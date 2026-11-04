# ==========================================
# 1. IMPORTS AT MGA CONFIGURATION
# ==========================================
import hashlib
import os
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from functools import wraps

import click
from flask import Flask, abort, flash, redirect, render_template, request, url_for
from flask_login import (LoginManager, UserMixin, current_user, login_required,
                         login_user, logout_user)
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import literal, or_
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadTimeSignature

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY", "dev-only-change-me"),
    # Supabase PostgreSQL Connection String (Transaction Pooler / Direct connection)
    SQLALCHEMY_DATABASE_URI=os.environ.get(
        "DATABASE_URL",
        "postgresql://postgres.lhqeemlgrizhalhdhojd:wendellartshed26@aws-0-ap-south-1.pooler.supabase.com:6543/postgres"
    ),
    SQLALCHEMY_ENGINE_OPTIONS={
        "pool_pre_ping": True,
        "pool_recycle": 300,
    },
    MAX_CONTENT_LENGTH=5 * 1024 * 1024,
    UPLOAD_FOLDER=os.path.join(app.static_folder, "uploads"),
    DEFAULT_COMMISSION_RATE=0.03  # 3% platform commission
)

ALLOWED_EXT = {"jpg", "jpeg", "png", "webp"}
POST_IMAGE_EXT = {"jpg", "jpeg", "png", "webp"}
POST_VIDEO_EXT = {"mp4", "webm"}

db = SQLAlchemy(app)
csrf = CSRFProtect(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Please log in to access your dashboard."
login_manager.login_message_category = "info"


# ==========================================
# 2. DATABASE MODELS
# ==========================================

class Artist(UserMixin, db.Model):
    """Modelo para sa mga User (Artists at Clients) pati na rin sa kanilang mga setting."""
    __tablename__ = "artist"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    age = db.Column(db.Integer, default=0)
    address = db.Column(db.String(200), default="")
    art_style = db.Column(db.String(100), default="figurative")
    art_subject = db.Column(db.String(100), default="landscape")
    art_medium = db.Column(db.String(100), default="oil")
    achievements = db.Column(db.Text, default="")
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    experience = db.Column(db.String(80), default="")
    bio = db.Column(db.Text, default="")
    sample_artworks = db.Column(db.Text, default="")  # Comma-separated filenames para sa portfolio/sample works
    account_type = db.Column(db.String(20), nullable=False, default="artist", server_default="artist")
    is_approved = db.Column(db.Boolean, nullable=False, default=False, server_default=db.text("false"))
    avatar = db.Column(db.String(120))
    cover_photo = db.Column(db.String(120))
    
    show_in_directory = db.Column(db.Boolean, nullable=False, default=True, server_default=db.text("true"))
    show_member_since = db.Column(db.Boolean, nullable=False, default=True, server_default=db.text("true"))
    notify_new_orders = db.Column(db.Boolean, nullable=False, default=True, server_default=db.text("true"))
    
    is_admin = db.Column(db.Boolean, nullable=False, default=False, server_default=db.text("false"))
    suspended = db.Column(db.Boolean, nullable=False, default=False, server_default=db.text("false"))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    works = db.relationship("Artwork", backref="artist", cascade="all, delete-orphan",
                            order_by="Artwork.created_at.desc()")
    conversations = db.relationship(
        "Conversation", backref="artist", cascade="all, delete-orphan",
        foreign_keys="Conversation.artist_id",
    )

    @property
    def initials(self):
        parts = self.name.split()
        return (parts[0][0] + parts[-1][0]).upper() if len(parts) > 1 else self.name[:2].upper()

    @property
    def slug(self):
        return f"artist-{self.id}"

    @property
    def is_active(self):  
        return not self.suspended

    @property
    def public_works(self):
        return [] if self.suspended or not self.is_approved else [w for w in self.works if not w.hidden]


class Artwork(db.Model):
    """Modelo para sa mga gawang sining o painting na naka-post."""
    __tablename__ = "artwork"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    size = db.Column(db.String(60), default="")
    note = db.Column(db.String(300), default="")
    image = db.Column(db.String(120))
    available = db.Column(db.Boolean, default=True)
    price = db.Column(db.Integer)
    views = db.Column(db.Integer, default=0, nullable=False, server_default=db.text("0"))
    
    style = db.Column(db.String(50), default="figurative")
    subject = db.Column(db.String(50), default="landscape")
    medium = db.Column(db.String(50), default="oil")
    
    hidden = db.Column(db.Boolean, nullable=False, default=False, server_default=db.text("false"))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    artist_id = db.Column(db.Integer, db.ForeignKey("artist.id"), nullable=False)

    @property
    def artist_name(self):
        return self.artist.name

    @property
    def price_label(self):
        return f"₱{self.price:,}" if self.price else "Price on request"

    @property
    def reserved(self):
        return any(o.status in ("pending", "payment_uploaded", "in_escrow") for o in self.orders)

    @property
    def can_buy(self):
        return bool(self.available and self.price and not self.reserved and self.is_public)

    @property
    def is_public(self):
        return not self.hidden and not self.artist.suspended and self.artist.is_approved

    @property
    def status_label(self):
        if not self.available:
            return "Sold"
        return "Reserved" if self.reserved else "Available"

    @property
    def colors(self):
        h = int(hashlib.md5(f"{self.id}{self.title}".encode()).hexdigest(), 16) % 360
        return [f"hsl({h} 45% 28%)", f"hsl({(h + 40) % 360} 70% 55%)",
                f"hsl({(h + 200) % 360} 40% 60%)"]


class Order(db.Model):
    """Order and admin-managed escrow/payout tracking."""
    __tablename__ = "purchase_order"
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(40), unique=True, nullable=False,
                      default=lambda: secrets.token_urlsafe(16))
    artwork_id = db.Column(db.Integer, db.ForeignKey("artwork.id"))
    artist_id = db.Column(db.Integer, db.ForeignKey("artist.id"), nullable=False, index=True)
    buyer_id = db.Column(db.Integer, db.ForeignKey("artist.id"), index=True)
    artwork_title = db.Column(db.String(120), nullable=False)
    price = db.Column(db.Integer, nullable=False)
    
    # Commission & Grace Period Fields (3%)
    commission_rate = db.Column(db.Float, nullable=False, default=0.03)
    commission_amount = db.Column(db.Integer, nullable=False, default=0)
    artist_payout = db.Column(db.Integer, nullable=False, default=0)
    funds_received = db.Column(db.Boolean, nullable=False, default=False, server_default=db.text("false"))
    funds_received_at = db.Column(db.DateTime)
    payout_recorded_at = db.Column(db.DateTime)
    payout_released = db.Column(db.Boolean, nullable=False, default=False, server_default=db.text("false"))
    payout_released_at = db.Column(db.DateTime)
    
    buyer_name = db.Column(db.String(80), nullable=False)
    buyer_email = db.Column(db.String(120), nullable=False)
    buyer_phone = db.Column(db.String(30), nullable=False)
    note = db.Column(db.String(500), default="")
    
    payment_proof = db.Column(db.String(120))
    status = db.Column(db.String(30), nullable=False, default="pending")
    received_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    artwork = db.relationship("Artwork", backref="orders")
    artist = db.relationship("Artist", foreign_keys=[artist_id], backref="orders")
    buyer = db.relationship("Artist", foreign_keys=[buyer_id])

    @property
    def price_label(self):
        return f"₱{self.price:,}"

    @property
    def commission_label(self):
        return f"₱{self.commission_amount:,}"

    @property
    def payout_label(self):
        return f"₱{self.artist_payout:,}"


class Notification(db.Model):
    __tablename__ = "notification"
    id = db.Column(db.Integer, primary_key=True)
    artist_id = db.Column(db.Integer, db.ForeignKey("artist.id"), nullable=False, index=True)
    message = db.Column(db.String(200), nullable=False)
    kind = db.Column(db.String(30), nullable=False, default="general", server_default="general")
    is_read = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    artist = db.relationship("Artist", backref=db.backref("notifications", cascade="all, delete-orphan"))


def notify_admins(message, kind):
    for admin in Artist.query.filter_by(is_admin=True).all():
        db.session.add(Notification(
            artist_id=admin.id,
            message=message,
            kind=kind,
        ))


class Conversation(db.Model):
    __tablename__ = "conversation"
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(64), unique=True, nullable=False,
                      default=lambda: secrets.token_urlsafe(32))
    artist_id = db.Column(db.Integer, db.ForeignKey("artist.id"), nullable=False, index=True)
    participant_artist_id = db.Column(db.Integer, db.ForeignKey("artist.id"), index=True)
    artwork_id = db.Column(db.Integer, db.ForeignKey("artwork.id", ondelete="SET NULL"))
    artwork_title = db.Column(db.String(120), nullable=False)
    client_name = db.Column(db.String(80), nullable=False)
    client_email = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    artwork = db.relationship("Artwork")
    participant_artist = db.relationship("Artist", foreign_keys=[participant_artist_id])
    messages = db.relationship(
        "ChatMessage", backref="conversation", cascade="all, delete-orphan",
        order_by="ChatMessage.created_at",
    )


class ChatMessage(db.Model):
    __tablename__ = "chat_message"
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey("conversation.id"), nullable=False, index=True)
    sender = db.Column(db.String(10), nullable=False)
    body = db.Column(db.String(2000), nullable=False)
    is_read = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class Post(db.Model):
    __tablename__ = "community_post"
    id = db.Column(db.Integer, primary_key=True)
    caption = db.Column(db.String(1000), nullable=False, default="")
    media_path = db.Column(db.String(120), nullable=False)
    media_type = db.Column(db.String(10), nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    user_id = db.Column(db.Integer, db.ForeignKey("artist.id"), nullable=False, index=True)
    
    artist = db.relationship("Artist", backref=db.backref("community_posts", cascade="all, delete-orphan"))
    likes = db.relationship("Like", backref="post", cascade="all, delete-orphan")
    comments = db.relationship(
        "Comment", backref="post", cascade="all, delete-orphan",
        order_by="Comment.timestamp",
    )


class Comment(db.Model):
    __tablename__ = 'comment'
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    post_id = db.Column(db.Integer, db.ForeignKey('community_post.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('artist.id'), nullable=False)
    user = db.relationship('Artist', backref=db.backref('comments', lazy=True, cascade="all, delete-orphan"))


class Like(db.Model):
    __tablename__ = 'like'
    id = db.Column(db.Integer, primary_key=True)
    reaction_type = db.Column(db.String(20), default='like')
    post_id = db.Column(db.Integer, db.ForeignKey('community_post.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('artist.id'), nullable=False)
    __table_args__ = (db.UniqueConstraint('user_id', 'post_id', name='unique_user_post_reaction'),)


# ==========================================
# 3. USER LOADER AT DATABASE MIGRATION CHECK
# ==========================================

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(Artist, int(user_id))


# Helper function para makuha ang mga column sa PostgreSQL gamit ang information_schema
def get_table_columns(table_name):
    result = db.session.execute(db.text(
        "SELECT column_name FROM information_schema.columns WHERE table_name = :tname"
    ), {"tname": table_name})
    return [row[0] for row in result]


with app.app_context():
    db.create_all()

    notification_cols = get_table_columns("notification")
    if "kind" not in notification_cols:
        db.session.execute(db.text(
            "ALTER TABLE notification ADD COLUMN kind "
            "VARCHAR(30) NOT NULL DEFAULT 'general'"
        ))
        db.session.commit()
    
    cols = get_table_columns("artist")
    for col, ddl in [
        ("account_type", "VARCHAR(20) NOT NULL DEFAULT 'artist'"),
        ("is_approved", "BOOLEAN NOT NULL DEFAULT false"),
        ("avatar", "VARCHAR(120)"),
        ("cover_photo", "VARCHAR(120)"),
        ("art_style", "VARCHAR(100) DEFAULT 'figurative'"),
        ("art_subject", "VARCHAR(100) DEFAULT 'landscape'"),
        ("art_medium", "VARCHAR(100) DEFAULT 'oil'"),
        ("sample_artworks", "TEXT DEFAULT ''"),
        ("show_in_directory", "BOOLEAN NOT NULL DEFAULT true"),
        ("show_member_since", "BOOLEAN NOT NULL DEFAULT true"),
        ("notify_new_orders", "BOOLEAN NOT NULL DEFAULT true"),
        ("is_admin", "BOOLEAN NOT NULL DEFAULT false"),
        ("suspended", "BOOLEAN NOT NULL DEFAULT false"),
    ]:
        if col not in cols:
            db.session.execute(db.text(f"ALTER TABLE artist ADD COLUMN {col} {ddl}"))
            db.session.commit()
            if col == "is_approved":
                db.session.execute(db.text(
                    "UPDATE artist SET is_approved = true "
                    "WHERE account_type = 'artist'"
                ))
                db.session.commit()
                
    art_cols = get_table_columns("artwork")
    for col, ddl in [
        ("price", "INTEGER"), 
        ("hidden", "BOOLEAN NOT NULL DEFAULT false"),
        ("style", "VARCHAR(50) DEFAULT 'figurative'"),
        ("subject", "VARCHAR(50) DEFAULT 'landscape'"),
        ("medium", "VARCHAR(50) DEFAULT 'oil'"),
        ("views", "INTEGER NOT NULL DEFAULT 0")
    ]:
        if col not in art_cols:
            db.session.execute(db.text(f"ALTER TABLE artwork ADD COLUMN {col} {ddl}"))
            db.session.commit()
            
    order_cols = get_table_columns("purchase_order")
    for col, ddl in [
        ("buyer_id", "INTEGER REFERENCES artist(id)"),
        ("commission_rate", "FLOAT NOT NULL DEFAULT 0.03"),
        ("commission_amount", "INTEGER NOT NULL DEFAULT 0"),
        ("artist_payout", "INTEGER NOT NULL DEFAULT 0"),
        ("funds_received", "BOOLEAN NOT NULL DEFAULT false"),
        ("funds_received_at", "TIMESTAMP WITHOUT TIME ZONE"),
        ("payout_recorded_at", "TIMESTAMP WITHOUT TIME ZONE"),
        ("payout_released", "BOOLEAN NOT NULL DEFAULT false"),
        ("payout_released_at", "TIMESTAMP WITHOUT TIME ZONE"),
        ("payment_proof", "VARCHAR(120)"),
        ("received_at", "TIMESTAMP WITHOUT TIME ZONE")
    ]:
        if col not in order_cols:
            db.session.execute(db.text(f"ALTER TABLE purchase_order ADD COLUMN {col} {ddl}"))
            db.session.commit()

    db.session.execute(db.text(
        "UPDATE purchase_order SET funds_received = true, "
        "funds_received_at = COALESCE(funds_received_at, created_at) "
        "WHERE status = 'in_escrow' AND funds_received = false"
    ))
    db.session.commit()

    db.session.execute(db.text(
        "CREATE INDEX IF NOT EXISTS ix_purchase_order_buyer_id ON purchase_order (buyer_id)"
    ))
    db.session.commit()
    
    conversation_cols = get_table_columns("conversation")
    if "participant_artist_id" not in conversation_cols:
        db.session.execute(db.text(
            "ALTER TABLE conversation ADD COLUMN participant_artist_id "
            "INTEGER REFERENCES artist(id)"
        ))
        db.session.commit()
    db.session.execute(db.text(
        "CREATE INDEX IF NOT EXISTS ix_conversation_participant_artist_id "
        "ON conversation (participant_artist_id)"
    ))
    db.session.commit()


# ==========================================
# 4. MGA HELPER FUNCTIONS AT DECORATORS
# ==========================================

def safe_next(target):
    if target and target.startswith("/") and not target.startswith("//") and "\\" not in target:
        return target
    if current_user.is_authenticated:
        if current_user.is_admin:
            return url_for("admin_dashboard")
        if current_user.account_type == "client":
            return url_for("messages")
        if current_user.account_type == "artist" and not current_user.is_approved:
            return url_for("artist_application_status")
    return url_for("dashboard")


def save_image(file):
    if not file or not file.filename:
        return None
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_EXT:
        raise ValueError("Only JPG, PNG, or WEBP images are accepted.")
    name = f"{uuid.uuid4().hex}.{ext}"
    file.save(os.path.join(app.config["UPLOAD_FOLDER"], name))
    return name


def save_post_media(file):
    if not file or not file.filename:
        raise ValueError("Choose an image or video to upload.")
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    header = file.stream.read(12)
    file.stream.seek(0)
    valid_media = {
        "jpg": header.startswith(b"\xff\xd8\xff"),
        "jpeg": header.startswith(b"\xff\xd8\xff"),
        "png": header.startswith(b"\x89PNG\r\n\x1a\n"),
        "webp": header.startswith(b"RIFF") and header[8:12] == b"WEBP",
        "mp4": len(header) >= 8 and header[4:8] == b"ftyp",
        "webm": header.startswith(b"\x1a\x45\xdf\xa3"),
    }
    if not valid_media.get(ext, False):
        raise ValueError("The uploaded file does not match its image or video extension.")
    if ext in POST_IMAGE_EXT:
        media_type = "image"
    elif ext in POST_VIDEO_EXT:
        media_type = "video"
    else:
        raise ValueError("Use a JPG, PNG, WEBP, MP4, or WEBM file.")
    name = f"{uuid.uuid4().hex}.{ext}"
    file.save(os.path.join(app.config["UPLOAD_FOLDER"], name))
    return name, media_type


def remove_image(name):
    if name:
        try:
            os.remove(os.path.join(app.config["UPLOAD_FOLDER"], name))
        except OSError:
            pass


def parse_price(raw):
    if not raw:
        return None, None
    raw = str(raw).replace(",", "").replace("₱", "").strip()
    if not raw:
        return None, None
    try:
        price = int(raw)
    except ValueError:
        return None, "Enter a valid price in pesos."
    if not (1 <= price <= 100_000_000):
        return None, "Enter a valid price in pesos (a whole number above zero), or leave it empty."
    return price, None


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^[0-9+()\-\s]{7,20}$")


def ensure_bootstrap_admin():
    email = os.environ.get("ADMIN_EMAIL", "admin@wendell26.com").strip().lower()
    password = os.environ.get("ADMIN_PASSWORD", "")
    if not password:
        if os.environ.get("ADMIN_EMAIL"):
            raise RuntimeError("ADMIN_PASSWORD is required when ADMIN_EMAIL is configured.")
        return
    if len(password) < 8 or password.isspace():
        raise RuntimeError("ADMIN_PASSWORD must contain at least 8 non-whitespace characters.")
    if not EMAIL_RE.fullmatch(email):
        raise RuntimeError("ADMIN_EMAIL must be a valid email address.")

    admin = Artist.query.filter(db.func.lower(Artist.email) == email).first()
    if admin is None:
        admin = Artist(
            name="Admin ArtHub",
            email=email,
            password_hash=generate_password_hash(password),
            account_type="artist",
            is_approved=True,
            is_admin=True,
            suspended=False,
        )
        db.session.add(admin)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            admin = Artist.query.filter(db.func.lower(Artist.email) == email).first()
            if admin is None:
                raise

    admin.is_admin = True
    admin.suspended = False
    if admin.account_type == "artist":
        admin.is_approved = True
    db.session.commit()


with app.app_context():
    ensure_bootstrap_admin()


# Helper functions para sa Password Reset Tokens
def get_serializer():
    return URLSafeTimedSerializer(app.config["SECRET_KEY"])

def generate_reset_token(email):
    serializer = get_serializer()
    return serializer.dumps(email, salt="password-reset-salt")

def verify_reset_token(token, expiration=3600):
    serializer = get_serializer()
    try:
        email = serializer.loads(token, salt="password-reset-salt", max_age=expiration)
        return email
    except (SignatureExpired, BadTimeSignature):
        return None


@app.context_processor
def inject_counts():
    if current_user.is_authenticated:
        counts = db.session.query(
            db.session.query(db.func.count(Order.id)).filter_by(
                artist_id=current_user.id, status="pending"
            ).scalar_subquery(),
            db.session.query(db.func.count(Notification.id)).filter_by(
                artist_id=current_user.id, is_read=False
            ).scalar_subquery(),
            db.session.query(db.func.count(ChatMessage.id)).join(Conversation).filter(
                or_(
                    db.and_(
                        Conversation.artist_id == current_user.id,
                        ChatMessage.sender == "client",
                    ),
                    db.and_(
                        Conversation.participant_artist_id == current_user.id,
                        ChatMessage.sender == "artist",
                    ),
                ),
                ChatMessage.is_read.is_(False),
            ).scalar_subquery(),
        ).one()
        return {
            "pending_orders": counts[0],
            "unread_notifications": counts[1],
            "unread_messages": counts[2],
        }
    return {"pending_orders": 0, "unread_notifications": 0, "unread_messages": 0}


@app.context_processor
def inject_dynamic_categories():
    visible_artwork_filters = (
        Artwork.hidden.is_(False),
        Artist.is_approved.is_(True),
        Artist.suspended.is_(False),
    )
    categories = (
        db.session.query(
            literal("style").label("category"), Artwork.style.label("value")
        )
        .join(Artist)
        .filter(*visible_artwork_filters, Artwork.style.isnot(None))
        .distinct()
        .union(
            db.session.query(
                literal("subject").label("category"), Artwork.subject.label("value")
            )
            .join(Artist)
            .filter(*visible_artwork_filters, Artwork.subject.isnot(None))
            .distinct(),
            db.session.query(
                literal("medium").label("category"), Artwork.medium.label("value")
            )
            .join(Artist)
            .filter(*visible_artwork_filters, Artwork.medium.isnot(None))
            .distinct(),
        )
        .all()
    )
    values_by_category = {"style": set(), "subject": set(), "medium": set()}
    for category, value in categories:
        if value:
            values_by_category[category].add(value.title())

    return {
        "dynamic_styles": sorted(values_by_category["style"]),
        "dynamic_subjects": sorted(values_by_category["subject"]),
        "dynamic_mediums": sorted(values_by_category["medium"]),
    }


@app.template_filter("ph_time")
def ph_time(dt):
    return (dt + timedelta(hours=8)).strftime("%B %d, %Y, %I:%M %p") if dt else ""


def visible_artworks():
    return (Artwork.query.join(Artist, Artwork.artist_id == Artist.id)
        .filter(Artwork.hidden.is_(False), Artist.suspended.is_(False),
            Artist.is_approved.is_(True)))


def can_see_private(owner_id):
    return current_user.is_authenticated and (current_user.id == owner_id or current_user.is_admin)


def admin_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return login_manager.unauthorized()
        if not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)
    return wrapper


def artist_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if current_user.account_type == "client":
            return redirect(url_for("messages"))
        if current_user.account_type != "artist":
            abort(403)
        if not current_user.is_approved:
            flash("Your artist application is waiting for admin approval.", "info")
            return redirect(url_for("artist_application_status"))
        return view(*args, **kwargs)
    return wrapper


def client_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("client_login", next=request.path))
        if current_user.account_type != "client":
            abort(403)
        return view(*args, **kwargs)
    return wrapper


def notifications_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return login_manager.unauthorized()
        if current_user.is_admin:
            return view(*args, **kwargs)
        if current_user.account_type == "client":
            return redirect(url_for("messages"))
        if not current_user.is_approved:
            flash("Your artist application is waiting for admin approval.", "info")
            return redirect(url_for("artist_application_status"))
        return view(*args, **kwargs)
    return wrapper


@app.before_request
def block_suspended_accounts():
    if current_user.is_authenticated and current_user.suspended:
        logout_user()
        flash("This account has been suspended or locked due to unpaid platform commissions. Please contact admin.", "error")
        return redirect(url_for("home"))


@app.cli.command("make-admin")
@click.argument("email")
def make_admin(email):
    artist = Artist.query.filter(db.func.lower(Artist.email) == email.strip().lower()).first()
    if not artist:
        click.echo("No account uses that email. Sign up on the site first, then run this again.")
        return
    artist.is_admin = True
    if artist.account_type == "artist":
        artist.is_approved = True
    db.session.commit()
    click.echo(f"{artist.name} ({artist.email}) is now an admin.")


# ==========================================
# 5. ROUTES AT MGA WEB PAGES
# ==========================================

@app.route("/")
def home():
    featured_paintings = visible_artworks().order_by(
        Artwork.views.desc(), Artwork.created_at.desc()
    ).limit(5).all()
    
    artists = Artist.query.filter_by(
        account_type="artist", is_approved=True, suspended=False, is_admin=False
    ).all()
    
    sales_by_artist = (
        db.session.query(
            Order.artist_id.label("artist_id"),
            db.func.sum(Order.price).label("sales"),
        )
        .filter(Order.status == "completed")
        .group_by(Order.artist_id)
        .subquery()
    )
    works_by_artist = (
        db.session.query(
            Artwork.artist_id.label("artist_id"),
            db.func.count(Artwork.id).label("works_count"),
        )
        .filter(Artwork.hidden.is_(False))
        .group_by(Artwork.artist_id)
        .subquery()
    )
    artist_scores = db.session.query(
        Artist,
        db.func.coalesce(sales_by_artist.c.sales, 0).label("sales"),
        db.func.coalesce(works_by_artist.c.works_count, 0).label("works_count"),
    ).outerjoin(
        sales_by_artist, sales_by_artist.c.artist_id == Artist.id
    ).outerjoin(
        works_by_artist, works_by_artist.c.artist_id == Artist.id
    ).filter(
        Artist.account_type == "artist",
        Artist.is_approved.is_(True),
        Artist.suspended.is_(False),
        Artist.is_admin.is_(False),
        Artist.show_in_directory.is_(True),
    ).all()

    top_artists_sorted = sorted(
        artist_scores,
        key=lambda row: (row.sales, row.works_count),
        reverse=True
    )[:5]

    featured_artists = [row.Artist for row in top_artists_sorted]
    featured_artist_work_counts = {
        row.Artist.id: row.works_count for row in top_artists_sorted
    }

    return render_template(
        "index.html",
        hero=featured_paintings[0] if featured_paintings else None,
        recent=featured_paintings,
        featured_artists=featured_artists,
        featured_artist_work_counts=featured_artist_work_counts,
        total_works=visible_artworks().count(),
        total_artists=len(artists),
    )


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(safe_next(None))
        
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = Artist.query.filter(db.func.lower(Artist.email) == email).first()
        
        if user:
            token = generate_reset_token(user.email)
            reset_url = url_for("reset_password", token=token, _external=True)
            
            print(f"\n==========================================")
            print(f"PASSWORD RESET LINK FOR {user.email}:")
            print(reset_url)
            print(f"==========================================\n")
            
            flash("If an account exists for that email, a password reset link has been sent.", "info")
            return redirect(url_for("login"))
        else:
            flash("No account is registered with that email address.", "error")
            
    return render_template("forgot_password.html")


@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(safe_next(None))
        
    email = verify_reset_token(token)
    if not email:
        flash("This password reset link has expired or is invalid. Please request a new one.", "error")
        return redirect(url_for("forgot_password"))
        
    user = Artist.query.filter(db.func.lower(Artist.email) == email).first_or_404()
    
    if request.method == "POST":
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        
        if len(password) < 8:
            flash("Password must be at least 8 characters.", "error")
        elif password != confirm:
            flash("Passwords do not match.", "error")
        else:
            user.password_hash = generate_password_hash(password)
            db.session.commit()
            flash("Your password has been changed. Log in with your new password.", "success")
            return redirect(url_for("login"))
            
    return render_template("reset_password.html", token=token)


@app.route("/community")
@login_required
def community():
    if current_user.account_type not in {"artist", "client"}:
        abort(403)
    posts = (Post.query.join(Artist)
             .filter(Artist.suspended.is_(False), Artist.is_approved.is_(True))
             .order_by(Post.timestamp.desc())
             .limit(50).all())
    post_ids = [post.id for post in posts]
    liked_ids = set()
    if current_user.is_authenticated and post_ids:
        liked_ids = {
            like.post_id for like in Like.query.filter(
                Like.user_id == current_user.id,
                Like.post_id.in_(post_ids),
            ).all()
        }
    return render_template("community.html", posts=posts, liked_ids=liked_ids)


@app.route("/community/posts", methods=["POST"])
@login_required
def create_post():
    if current_user.account_type != "artist" or not current_user.is_approved:
        abort(403)

    caption = request.form.get("caption", "").strip()
    file = request.files.get("media")

    if not caption and (not file or not file.filename):
        flash("Add a caption or choose an image or video to create a post.", "error")
        return redirect(url_for("community"))

    if len(caption) > 1000:
        flash("Caption must be 1,000 characters or fewer.", "error")
        return redirect(url_for("community"))

    media_path = ""
    media_type = "none"

    if file and file.filename:
        try:
            media_path, media_type = save_post_media(file)
        except ValueError as error:
            flash(str(error), "error")
            return redirect(url_for("community"))

    db.session.add(Post(
        caption=caption,
        media_path=media_path,
        media_type=media_type,
        user_id=current_user.id,
    ))
    db.session.commit()
    flash("Your post has been shared with the community.", "success")
    return redirect(url_for("community"))


@app.route("/community/posts/<int:post_id>/delete", methods=["POST"])
@login_required
def delete_post(post_id):
    post = db.get_or_404(Post, post_id)
    if post.user_id != current_user.id:
        abort(403)

    media_path = post.media_path
    db.session.delete(post)
    db.session.commit()
    remove_image(media_path)
    flash("Your post has been deleted.", "info")
    return redirect(url_for("community"))


@app.route("/community/posts/<int:post_id>/comment", methods=["POST"])
@login_required
def add_comment(post_id):
    post = db.get_or_404(Post, post_id)
    content = request.form.get("content", "").strip()
    if content:
        comment = Comment(content=content, post_id=post.id, user_id=current_user.id)
        db.session.add(comment)
        
        if post.user_id != current_user.id:
            msg = f"{current_user.name} commented on your community post."
            db.session.add(Notification(artist_id=post.user_id, message=msg))
            
        db.session.commit()
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return {
                "success": True,
                "comment_id": comment.id,
                "content": comment.content,
                "user_name": current_user.name,
                "user_avatar": current_user.avatar or '',
                "user_initials": current_user.initials
            }
            
    return redirect(url_for("community"))


@app.route("/community/comments/<int:comment_id>/edit", methods=["POST"])
@login_required
def edit_comment(comment_id):
    comment = db.get_or_404(Comment, comment_id)
    if comment.user_id != current_user.id:
        abort(403)
    content = request.form.get("content", "").strip()
    if content:
        comment.content = content
        db.session.commit()
    return redirect(url_for("community"))


@app.route("/community/comments/<int:comment_id>/delete", methods=["POST"])
@login_required
def delete_comment(comment_id):
    comment = db.get_or_404(Comment, comment_id)
    if comment.user_id != current_user.id:
        abort(403)
    db.session.delete(comment)
    db.session.commit()
    return redirect(url_for("community"))


@app.route("/community/posts/<int:post_id>/react/<string:reaction_type>", methods=["POST"])
@login_required
def react_post(post_id, reaction_type):
    post = db.get_or_404(Post, post_id)
    existing_like = Like.query.filter_by(user_id=current_user.id, post_id=post.id).first()
    
    current_user_reaction = None
    if existing_like:
        if existing_like.reaction_type == reaction_type:
            db.session.delete(existing_like)
        else:
            existing_like.reaction_type = reaction_type
            current_user_reaction = reaction_type
    else:
        new_like = Like(user_id=current_user.id, post_id=post.id, reaction_type=reaction_type)
        db.session.add(new_like)
        current_user_reaction = reaction_type
        
        if post.user_id != current_user.id:
            emoji = "👍" if reaction_type == "like" else "❤️"
            msg = f"{current_user.name} reacted {emoji} to your community post."
            db.session.add(Notification(artist_id=post.user_id, message=msg))
        
    db.session.commit()
    
    like_count = Like.query.filter_by(post_id=post.id, reaction_type='like').count()
    heart_count = Like.query.filter_by(post_id=post.id, reaction_type='heart').count()

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return {
            "success": True,
            "like_count": like_count,
            "heart_count": heart_count,
            "user_reaction": current_user_reaction
        }
        
    return redirect(url_for("community"))


@app.route("/community/posts/<int:post_id>/like", methods=["POST"])
@login_required
def toggle_post_like(post_id):
    post = db.get_or_404(Post, post_id)
    if post.artist.suspended:
        abort(404)
    existing = Like.query.filter_by(post_id=post.id, user_id=current_user.id).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()
    else:
        db.session.add(Like(post_id=post.id, user_id=current_user.id))
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash("You already liked this post.", "info")
    return redirect(url_for("community"))


@app.route("/community/posts/<int:post_id>/comments", methods=["POST"])
@login_required
def add_post_comment(post_id):
    post = db.get_or_404(Post, post_id)
    if post.artist.suspended:
        abort(404)
    body = request.form.get("body", "").strip()
    if not body or len(body) > 1000:
        flash("Comment must be between 1 and 1,000 characters.", "error")
        return redirect(url_for("community"))

    db.session.add(Comment(post_id=post.id, user_id=current_user.id, content=body))
    db.session.commit()
    flash("Your comment has been added.", "success")
    return redirect(url_for("community"))


@app.route("/artists")
def artists():
    return render_template("artists.html", artists=Artist.query.filter_by(
        account_type="artist", is_approved=True, show_in_directory=True,
        suspended=False, is_admin=False).order_by(Artist.name).all())


@app.route("/artists/<int:artist_id>")
def artist_detail(artist_id):
    artist = db.get_or_404(Artist, artist_id)
    if artist.account_type != "artist" and not current_user.is_admin:
        abort(404)
    privileged = can_see_private(artist.id)
    if (artist.suspended or not artist.is_approved) and not privileged:
        abort(404)
    works = artist.works if privileged else artist.public_works
    return render_template("artist.html", artist=artist, works=works)


@app.route("/artists/<int:artist_id>/message", methods=["GET", "POST"])
@client_required
def artist_message(artist_id):
    recipient = db.get_or_404(Artist, artist_id)
    if recipient.account_type != "artist" or recipient.suspended or not recipient.is_approved:
        abort(404)
    if recipient.id == current_user.id:
        abort(403)

    if current_user.account_type == "client":
        owner_id, participant_id = recipient.id, current_user.id
    else:
        owner_id, participant_id = sorted((current_user.id, recipient.id))
    conversation = Conversation.query.filter(
        Conversation.participant_artist_id == participant_id,
        Conversation.artist_id == owner_id,
    ).first()
    if request.method == "POST":
        body = request.form.get("message", "").strip()
        if not body or len(body) > 2000:
            flash("Enter a message (up to 2,000 characters).", "error")
            return render_template(
                "new_artist_message.html", artist=recipient, message=body,
            ), 400

        if conversation is None:
            participant = db.session.get(Artist, participant_id)
            conversation = Conversation(
                artist_id=owner_id,
                participant_artist_id=participant_id,
                artwork_title="Artist conversation",
                client_name=participant.name,
                client_email=participant.email,
            )
            db.session.add(conversation)
            db.session.flush()

        sender = "artist" if current_user.id == owner_id else "client"
        conversation.messages.append(ChatMessage(sender=sender, body=body))
        conversation.updated_at = datetime.now(timezone.utc)
        db.session.commit()
        return redirect(url_for("artist_conversation", conversation_id=conversation.id))

    if conversation:
        return redirect(url_for("artist_conversation", conversation_id=conversation.id))
    return render_template("new_artist_message.html", artist=recipient, message="")


@app.route("/artworks/<int:artwork_id>")
def artwork_detail(artwork_id):
    artwork = db.get_or_404(Artwork, artwork_id)
    if not artwork.is_public and not can_see_private(artwork.artist_id):
        abort(404)
    
    artwork.views = (artwork.views or 0) + 1
    db.session.commit()

    more = [w for w in artwork.artist.public_works if w.id != artwork.id][:3]
    return render_template("artwork.html", artwork=artwork, more=more)


@app.route("/artwork/<int:artwork_id>/message", methods=["GET", "POST"])
@client_required
def new_conversation(artwork_id):
    artwork = db.get_or_404(Artwork, artwork_id)
    if not artwork.is_public:
        abort(404)
    if current_user.id == artwork.artist_id:
        abort(403)

    form, errors = request.form, {}
    if request.method == "POST":
        name = current_user.name
        email = current_user.email
        body = form.get("message", "").strip()
        if not body or len(body) > 2000:
            errors["message"] = "Enter a message (up to 2,000 characters)."
        if not errors:
            conversation = Conversation(
                artist_id=artwork.artist_id,
                participant_artist_id=current_user.id,
                artwork_id=artwork.id,
                artwork_title=artwork.title,
                client_name=name,
                client_email=email,
                messages=[ChatMessage(sender="client", body=body)],
            )
            db.session.add(conversation)
            db.session.commit()
            flash("Your message has been sent. Continue the conversation from Messages.", "success")
            return redirect(url_for("artist_conversation", conversation_id=conversation.id))
        flash("Please fix the highlighted fields.", "error")
        return render_template(
            "new_message.html", artwork=artwork, form=form, errors=errors,
        ), 400
    return render_template("new_message.html", artwork=artwork, form=form, errors=errors)


@app.route("/conversation/<token>", methods=["GET", "POST"])
def client_conversation(token):
    conversation = Conversation.query.filter_by(token=token).first_or_404()
    if conversation.participant_artist_id is not None:
        if not current_user.is_authenticated or current_user.id not in (
            conversation.artist_id, conversation.participant_artist_id,
        ):
            abort(403)
        return redirect(url_for("artist_conversation", conversation_id=conversation.id))
    if not current_user.is_authenticated:
        return redirect(url_for("client_login", next=request.path))
    if current_user.account_type == "client":
        if current_user.email != conversation.client_email:
            abort(403)
        conversation.participant_artist_id = current_user.id
        db.session.commit()
        return redirect(url_for("artist_conversation", conversation_id=conversation.id))
    if current_user.id == conversation.artist_id:
        return redirect(url_for("artist_conversation", conversation_id=conversation.id))
    abort(403)


@app.route("/messages")
@login_required
def messages():
    conversations = Conversation.query.filter(or_(
        Conversation.artist_id == current_user.id,
        Conversation.participant_artist_id == current_user.id,
    )).order_by(Conversation.updated_at.desc()).all()
    return render_template("messages.html", conversations=conversations)


@app.route("/messages/<int:conversation_id>", methods=["GET", "POST"])
@login_required
def artist_conversation(conversation_id):
    conversation = Conversation.query.filter(
        Conversation.id == conversation_id,
        or_(
            Conversation.artist_id == current_user.id,
            Conversation.participant_artist_id == current_user.id,
        ),
    ).first_or_404()
    viewer_sender = "artist" if current_user.id == conversation.artist_id else "client"
    other_sender = "client" if viewer_sender == "artist" else "artist"
    if request.method == "POST":
        body = request.form.get("message", "").strip()
        if not body or len(body) > 2000:
            flash("Enter a message (up to 2,000 characters).", "error")
            return redirect(url_for("artist_conversation", conversation_id=conversation.id))
        conversation.messages.append(ChatMessage(sender=viewer_sender, body=body))
        conversation.updated_at = datetime.now(timezone.utc)
        db.session.commit()
        flash("Your reply has been sent.", "success")
        return redirect(url_for("artist_conversation", conversation_id=conversation.id))

    ChatMessage.query.filter_by(
        conversation_id=conversation.id, sender=other_sender, is_read=False,
    ).update({"is_read": True}, synchronize_session=False)
    db.session.commit()
    return render_template(
        "conversation.html", conversation=conversation, artist_view=True,
        viewer_sender=viewer_sender,
    )


@app.route("/messages/<int:conversation_id>/delete", methods=["POST"])
@login_required
def delete_conversation(conversation_id):
    conversation = Conversation.query.filter(
        Conversation.id == conversation_id,
        or_(
            Conversation.artist_id == current_user.id,
            Conversation.participant_artist_id == current_user.id,
        ),
    ).first_or_404()
    db.session.delete(conversation)
    db.session.commit()
    flash("Conversation deleted.", "info")
    return redirect(url_for("messages"))


@app.route("/artworks")
def artworks():
    style = request.args.get("style", "").strip().lower()
    subject = request.args.get("subject", "").strip().lower()
    medium = request.args.get("medium", "").strip().lower()

    query = visible_artworks()

    if style:
        query = query.filter(db.func.lower(Artwork.style) == style)
    if subject:
        query = query.filter(db.func.lower(Artwork.subject) == subject)
    if medium:
        query = query.filter(db.func.lower(Artwork.medium) == medium)

    paintings = query.order_by(Artwork.created_at.desc()).all()
    return render_template(
        "artworks.html", 
        paintings=paintings, 
        current_style=style, 
        current_subject=subject, 
        current_medium=medium
    )


@app.route("/search")
def search():
    query = request.args.get("q", "").strip()[:100]
    paintings = []
    artists = []
    if query:
        pattern = f"%{query}%"
        paintings = (visible_artworks()
                     .filter(or_(Artwork.title.ilike(pattern), Artist.name.ilike(pattern)))
                     .order_by(Artwork.created_at.desc()).limit(50).all())
        artists = (Artist.query.filter_by(
            account_type="artist", is_approved=True,
            show_in_directory=True, suspended=False,
        ).filter(Artist.name.ilike(pattern)).order_by(Artist.name).limit(50).all())
    return render_template("search.html", query=query, paintings=paintings, artists=artists)


@app.route("/register", methods=["GET", "POST"])
def register():
    return register_account("artist")


@app.route("/client/register", methods=["GET", "POST"])
def client_register():
    return register_account("client")


@app.route("/artist/application")
@login_required
def artist_application_status():
    if current_user.is_admin:
        return redirect(url_for("admin_dashboard"))
    if current_user.account_type != "artist":
        return redirect(url_for("messages"))
    if current_user.is_approved:
        return redirect(url_for("dashboard"))
    return render_template("artist_application_status.html")


@app.route("/client/apply-as-artist", methods=["GET", "POST"])
@login_required
@client_required
def client_apply_as_artist():
    form = request.form if request.method == "POST" else {
        "art_style": current_user.art_style or "figurative",
        "art_subject": current_user.art_subject or "landscape",
        "art_medium": current_user.art_medium or "oil",
        "experience": current_user.experience or "",
        "bio": current_user.bio or "",
    }
    errors = {}
    if request.method == "POST":
        current_user.account_type = "artist"
        current_user.is_approved = False
        current_user.show_in_directory = False
        current_user.art_style = form.get("art_style", "figurative").strip()[:80].lower()
        current_user.art_subject = form.get("art_subject", "landscape").strip()[:80].lower()
        current_user.art_medium = form.get("art_medium", "oil").strip()[:80].lower()
        current_user.experience = form.get("experience", "").strip()[:80]
        current_user.bio = form.get("bio", "").strip()[:600]
        
        sample_files = request.files.getlist("sample_artworks")
        sample_filenames = []
        for file in sample_files:
            if file and file.filename:
                try:
                    saved_name = save_image(file)
                    if saved_name:
                        sample_filenames.append(saved_name)
                except ValueError:
                    pass
        if sample_filenames:
            current_user.sample_artworks = ",".join(sample_filenames)

        notify_admins(
            f"New artist application: {current_user.name} ({current_user.email}) is awaiting review.",
            "artist_application",
        )
        db.session.commit()
        flash("Your artist application has been submitted and is awaiting admin approval.", "success")
        return redirect(url_for("artist_application_status"))
    return render_template("artist_application_form.html", form=form, errors=errors)


def register_account(account_type):
    if current_user.is_authenticated:
        if current_user.is_admin:
            return redirect(url_for("admin_dashboard"))
        if current_user.account_type == "client" and account_type != "artist":
            return redirect(url_for("messages"))
        if current_user.account_type == "artist":
            return redirect(url_for(
                "dashboard" if current_user.is_approved else "artist_application_status"
            ))
            
    form = request.form
    errors = {}
    if request.method == "POST":
        name = form.get("name", "").strip()
        email = form.get("email", "").strip().lower()
        password = form.get("password", "")
        if len(name) < 2:
            errors["name"] = "Enter your full name."
        if "@" not in email or "." not in email.split("@")[-1]:
            errors["email"] = "Enter a valid email address."
        else:
            existing_account = Artist.query.filter(
                db.func.lower(Artist.email) == email,
            ).first()
            if existing_account and account_type == "artist" and existing_account.account_type == "client":
                errors["email"] = "This Gmail already has a client account. Log in and use Apply as artist from your account menu."
            elif existing_account:
                errors["email"] = "This email is already in use. Log in to the existing account."
        if len(password) < 8:
            errors["password"] = "Password must be at least 8 characters."
        elif password != form.get("confirm", ""):
            errors["confirm"] = "Passwords do not match."
        
        sample_str = ""
        if account_type == "artist":
            sample_files = request.files.getlist("sample_artworks")
            sample_filenames = []
            for file in sample_files:
                if file and file.filename:
                    try:
                        saved_name = save_image(file)
                        if saved_name:
                            sample_filenames.append(saved_name)
                    except ValueError:
                        pass
            sample_str = ",".join(sample_filenames)

        if not errors:
            artist = Artist(
                name=name, email=email,
                account_type=account_type,
                is_approved=account_type == "client",
                password_hash=generate_password_hash(password),
                art_style=form.get("art_style", "figurative").strip()[:80].lower() if account_type == "artist" else "",
                art_subject=form.get("art_subject", "landscape").strip()[:80].lower() if account_type == "artist" else "",
                art_medium=form.get("art_medium", "oil").strip()[:80].lower() if account_type == "artist" else "",
                sample_artworks=sample_str,
                experience=form.get("experience", "").strip()[:80] if account_type == "artist" else "",
                bio=form.get("bio", "").strip()[:600] if account_type == "artist" else "",
            )
            db.session.add(artist)
            try:
                if account_type == "artist":
                    db.session.flush()
                    notify_admins(
                        f"New artist application: {artist.name} ({artist.email}) is awaiting review.",
                        "artist_application",
                    )
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                errors["email"] = "This email is already in use. Use a different email or log in."
            else:
                login_user(artist)
                if account_type == "client":
                    flash("Your client account is ready. You can now message artists and join the community.", "success")
                    return redirect(safe_next(request.args.get("next")))
                flash("Your artist application has been submitted and is awaiting admin approval.", "success")
                return redirect(url_for("artist_application_status"))
        flash("Please fix the highlighted fields.", "error")
        return render_template("register.html", form=form, errors=errors, account_type=account_type), 400
    return render_template("register.html", form=form, errors=errors, account_type=account_type)


@app.route("/login")
def login():
    if current_user.is_authenticated:
        if current_user.is_admin:
            return redirect(url_for("admin_dashboard"))
        if current_user.account_type == "client":
            return redirect(url_for("messages"))
        return redirect(url_for(
            "dashboard" if current_user.is_approved else "artist_application_status"
        ))

    return render_template("login_choice.html", next_url=request.args.get("next", ""))


@app.route("/artist/login", methods=["GET", "POST"])
def artist_login():
    return login_account("artist")


@app.route("/client/login", methods=["GET", "POST"])
def client_login():
    return login_account("client")


def login_account(account_type):
    if current_user.is_authenticated:
        if current_user.is_admin:
            return redirect(url_for("admin_dashboard"))
        if current_user.account_type == "client":
            return redirect(url_for("messages"))
        return redirect(url_for(
            "dashboard" if current_user.is_approved else "artist_application_status"
        ))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        artist = Artist.query.filter_by(email=email).first()
        if artist and check_password_hash(artist.password_hash, request.form.get("password", "")):
            if artist.suspended:
                flash("This account has been suspended. Please contact the administrator.", "error")
                return render_template("login.html", email=email, account_type=account_type), 403

            if artist.account_type != account_type:
                flash("This account uses the other sign-in option.", "error")
                return render_template(
                    "login.html", email=email, account_type=account_type,
                    next_url=request.args.get("next", ""),
                ), 403

            login_user(artist, remember=bool(request.form.get("remember")))

            if artist.is_admin:
                return redirect(url_for("admin_dashboard"))

            if artist.account_type == "artist" and not artist.is_approved:
                flash("Your artist application is waiting for admin approval.", "info")
                return redirect(url_for("artist_application_status"))

            return redirect(safe_next(request.args.get("next")))

        flash("Incorrect email or password.", "error")
        return render_template(
            "login.html", email=email, account_type=account_type,
            next_url=request.args.get("next", ""),
        ), 401

    return render_template(
        "login.html", email="", account_type=account_type,
        next_url=request.args.get("next", ""),
    )


@app.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("home"))


@app.route("/dashboard", methods=["GET", "POST"])
@login_required
@artist_required
def dashboard():
    if current_user.is_admin:
        return redirect(url_for("admin_dashboard"))

    if request.method == "POST":
        action = request.form.get("action")
        if action == "create_feed_post":
            caption = request.form.get("caption", "").strip()
            try:
                media_path, media_type = save_post_media(request.files.get("media"))
            except ValueError as e:
                flash(str(e), "error")
                return redirect(url_for("dashboard"))

            db.session.add(Post(caption=caption, media_path=media_path, media_type=media_type, user_id=current_user.id))
            db.session.commit()
            flash("Posted to your Newsfeed wall!", "success")
            return redirect(url_for("dashboard"))

    wall_posts = Post.query.filter_by(user_id=current_user.id).order_by(Post.timestamp.desc()).all()
    return render_template("dashboard.html", wall_posts=wall_posts)


@app.route("/my-artworks", methods=["GET", "POST"])
@login_required
@artist_required
def my_artworks():
    if current_user.is_admin:
        return redirect(url_for("admin_dashboard"))

    now_year = datetime.now().year
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        year = request.form.get("year", type=int) or now_year
        price, price_err = parse_price(request.form.get("price", ""))
        
        style = request.form.get("style", "").strip().lower()
        subject = request.form.get("subject", "").strip().lower()
        medium = request.form.get("medium", "").strip().lower()
        
        if price_err:
            flash(price_err, "error")
            return redirect(url_for("my_artworks"))

        try:
            image = save_image(request.files.get("image"))
        except ValueError as e:
            flash(str(e), "error")
            return redirect(url_for("my_artworks"))

        db.session.add(Artwork(
            title=title, year=year, price=price,
            style=style or "figurative", 
            subject=subject or "landscape", 
            medium=medium or "oil",
            size=request.form.get("size", "").strip()[:60],
            note=request.form.get("note", "").strip()[:300],
            available=bool(request.form.get("available")),
            image=image, artist_id=current_user.id
        ))
        db.session.commit()
        flash(f"Artwork “{title}” successfully uploaded!", "success")
        return redirect(url_for("my_artworks"))

    artworks = current_user.works
    return render_template("my_artworks.html", artworks=artworks, now_year=now_year)


@app.route("/artwork/<int:artwork_id>/edit", methods=["GET", "POST"])
@login_required
@artist_required
def edit_artwork(artwork_id):
    artwork = Artwork.query.get_or_404(artwork_id)
    if artwork.artist_id != current_user.id:
        abort(403)

    now_year = datetime.now().year
    if request.method == "POST":
        artwork.title = request.form.get("title", "").strip()[:120]
        artwork.year = request.form.get("year", type=int) or now_year
        price, price_err = parse_price(request.form.get("price", ""))
        if not price_err:
            artwork.price = price
        artwork.size = request.form.get("size", "").strip()[:60]
        
        style = request.form.get("style", "").strip().lower()
        subject = request.form.get("subject", "").strip().lower()
        medium = request.form.get("medium", "").strip().lower()

        if style:
            artwork.style = style
        if subject:
            artwork.subject = subject
        if medium:
            artwork.medium = medium

        artwork.note = request.form.get("note", "").strip()[:300]
        artwork.available = bool(request.form.get("available"))

        if request.files.get("image"):
            try:
                new_image = save_image(request.files.get("image"))
                if artwork.image:
                    remove_image(artwork.image)
                artwork.image = new_image
            except ValueError as e:
                flash(str(e), "error")
                return redirect(url_for("edit_artwork", artwork_id=artwork.id))

        db.session.commit()
        flash(f"Artwork “{artwork.title}” has been updated.", "success")
        return redirect(url_for("my_artworks"))

    return render_template("edit_artwork.html", artwork=artwork, now_year=now_year)


@app.route("/artwork/<int:artwork_id>/delete", methods=["POST"])
@login_required
@artist_required
def delete_artwork(artwork_id):
    artwork = db.get_or_404(Artwork, artwork_id)
    if artwork.artist_id != current_user.id:
        abort(403)
    if artwork.image:
        remove_image(artwork.image)
    db.session.delete(artwork)
    db.session.commit()
    flash("Artwork deleted.", "info")
    return redirect(url_for("my_artworks"))


@app.route("/profile", methods=["GET", "POST"])
@login_required
@artist_required
def profile():
    if current_user.is_admin:
        return redirect(url_for("admin_dashboard"))

    errors = {}
    
    form = request.form if request.method == "POST" else {
        "name": current_user.name,
        "age": current_user.age or "",
        "address": current_user.address or "",
        "art_style": current_user.art_style or "figurative",
        "art_subject": current_user.art_subject or "landscape",
        "art_medium": current_user.art_medium or "oil",
        "experience": current_user.experience or "",
        "achievements": current_user.achievements or "",
        "bio": current_user.bio or "",
    }

    if request.method == "POST":
        current_user.name = form.get("name", "").strip()[:80]
        try:
            current_user.age = int(form.get("age") or 0)
        except ValueError:
            current_user.age = 0
            
        current_user.address = form.get("address", "").strip()[:200]
        current_user.art_style = form.get("art_style", "figurative").strip()[:100].lower()
        current_user.art_subject = form.get("art_subject", "landscape").strip()[:100].lower()
        current_user.art_medium = form.get("art_medium", "oil").strip()[:100].lower()
        current_user.experience = form.get("experience", "").strip()[:80]
        current_user.achievements = form.get("achievements", "").strip()[:200]
        current_user.bio = form.get("bio", "").strip()[:600]

        if not errors:
            db.session.commit()
            flash("Your profile details have been saved.", "success")
            return redirect(url_for("dashboard"))
        
        flash("Please fix the highlighted fields.", "error")

    return render_template("profile.html", form=form, errors=errors)


@app.route("/profile/upload-cropped", methods=["POST"])
@login_required
@artist_required
def upload_cropped_image():
    file = request.files.get("file")
    upload_type = request.form.get("type")
    
    if not file:
        return {"success": False, "error": "No file uploaded"}, 400
        
    try:
        name = f"{uuid.uuid4().hex}.jpg"
        file.save(os.path.join(app.config["UPLOAD_FOLDER"], name))
        
        if upload_type == "avatar":
            if current_user.avatar:
                remove_image(current_user.avatar)
            current_user.avatar = name
        elif upload_type == "cover":
            if current_user.cover_photo:
                remove_image(current_user.cover_photo)
            current_user.cover_photo = name
            
        db.session.commit()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}, 500


@app.route("/profile/avatar/delete", methods=["POST"])
@login_required
@artist_required
def delete_avatar():
    if current_user.avatar:
        remove_image(current_user.avatar)
        current_user.avatar = None
        db.session.commit()
        flash("Your profile picture has been removed.", "info")
    return redirect(url_for("profile"))


@app.route("/artworks/<int:artwork_id>/buy", methods=["GET", "POST"])
@client_required
def checkout(artwork_id):
    artwork = db.get_or_404(Artwork, artwork_id)
    if not artwork.is_public:
        abort(404)
    detail = redirect(url_for("artwork_detail", artwork_id=artwork.id))
    if current_user.id == artwork.artist_id:
        flash("You can’t buy your own artwork.", "info")
        return detail
    if not artwork.can_buy:
        flash("This artwork is not available for purchase right now.", "info")
        return detail

    form = request.form if request.method == "POST" else {
        "name": current_user.name,
        "email": current_user.email,
    }
    errors = {}
    if request.method == "POST":
        name = form.get("name", "").strip()
        email = form.get("email", "").strip().lower()
        phone = form.get("phone", "").strip()
        if len(name) < 2:
            errors["name"] = "Enter your full name."
        if not EMAIL_RE.match(email):
            errors["email"] = "Enter a valid email address."
        if not PHONE_RE.match(phone):
            errors["phone"] = "Enter a valid phone number so the artist can reach you."
        if not errors:
            rate = app.config["DEFAULT_COMMISSION_RATE"] # 3%
            comm_amt = int(artwork.price * rate)
            payout = artwork.price - comm_amt

            order = Order(
                artwork_id=artwork.id, artist_id=artwork.artist_id,
                buyer_id=current_user.id,
                artwork_title=artwork.title, price=artwork.price,
                commission_rate=rate,
                commission_amount=comm_amt,
                artist_payout=payout,
                buyer_name=name[:80], buyer_email=email[:120], buyer_phone=phone,
                note=form.get("note", "").strip()[:500],
                status="pending"
            )
            db.session.add(order)
            db.session.flush()

            notify_admins(
                f"New checkout: Order #{order.id} — {order.buyer_name} ordered "
                f"“{artwork.title}” ({order.price_label}) from {artwork.artist.name}.",
                "order",
            )

            db.session.commit()
            return redirect(url_for("order_status", token=order.token))
        flash("Please fix the highlighted fields.", "error")
        return render_template("checkout.html", artwork=artwork, form=form, errors=errors), 400
    return render_template("checkout.html", artwork=artwork, form=form, errors=errors)


@app.route("/order/<token>/upload-payment", methods=["POST"])
@login_required
def upload_payment_proof(token):
    order = Order.query.filter_by(token=token).first_or_404()
    if current_user.id != order.buyer_id:
        abort(403)
    if order.status not in ("pending", "payment_uploaded"):
        flash("Payment proof can only be uploaded while the order is awaiting payment verification.", "error")
        return redirect(url_for("order_status", token=order.token))

    file = request.files.get("payment_proof")
    if not file or not file.filename:
        flash("Please select an image of your payment receipt.", "error")
        return redirect(url_for("order_status", token=order.token))
    try:
        filename = save_image(file)
    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("order_status", token=order.token))

    order.payment_proof = filename
    order.status = "payment_uploaded"
    notify_admins(
        f"Payment receipt uploaded for Order #{order.id} ({order.artwork_title}). Please review it.",
        "order",
    )
    db.session.commit()
    flash("Proof of payment submitted to admin for verification.", "success")
    return redirect(url_for("order_status", token=order.token))


@app.route("/admin/orders/<int:order_id>/verify-payment", methods=["POST"])
@admin_required
def admin_verify_payment(order_id):
    order = db.get_or_404(Order, order_id)
    if order.status != "payment_uploaded" or not order.payment_proof:
        flash("Only orders with an uploaded payment receipt can be verified.", "error")
        return redirect(url_for("admin_orders"))

    now = datetime.now(timezone.utc)
    changed = Order.query.filter_by(
        id=order.id, status="payment_uploaded", funds_received=False,
    ).filter(Order.payment_proof.is_not(None)).update(
        {
            Order.status: "in_escrow",
            Order.funds_received: True,
            Order.funds_received_at: now,
        },
        synchronize_session=False,
    )
    if not changed:
        db.session.rollback()
        flash("This payment was already verified or its status has changed.", "error")
        return redirect(url_for("admin_orders"))

    db.session.add(Notification(
        artist_id=order.artist_id,
        message=f"Admin approved the order for your artwork “{order.artwork_title}” ({order.price_label}). Please prepare it.",
        kind="order",
    ))
    db.session.commit()
    flash(f"Payment for Order #{order.id} is verified and recorded as held in escrow.", "success")
    return redirect(url_for("admin_orders"))


@app.route("/order/<token>/confirm-received", methods=["POST"])
@login_required
def client_confirm_received(token):
    order = Order.query.filter_by(token=token).first_or_404()
    if current_user.id != order.buyer_id:
        abort(403)

    if request.form.get("confirm_received") != "yes":
        flash("Please confirm that you have received the artwork before completing the order.", "error")
        return redirect(url_for("order_status", token=order.token))

    if order.status != "in_escrow" or not order.funds_received:
        flash("You can confirm receipt only after the admin verifies your payment and secures it in escrow.", "error")
        return redirect(url_for("order_status", token=order.token))

    now = datetime.now(timezone.utc)
    changed = Order.query.filter_by(
        id=order.id, buyer_id=current_user.id, status="in_escrow",
        funds_received=True, payout_recorded_at=None,
    ).update(
        {
            Order.status: "completed",
            Order.received_at: now,
            Order.payout_recorded_at: now,
        },
        synchronize_session=False,
    )
    if not changed:
        db.session.rollback()
        flash("This order was already confirmed or its status has changed.", "error")
        return redirect(url_for("order_status", token=order.token))

    if order.artwork:
        order.artwork.available = False

    db.session.add(Notification(
        artist_id=order.artist_id,
        message=f"Client confirmed receipt of Order #{order.id} ('{order.artwork_title}'). Your net payout of {order.payout_label} (after the 3% platform fee) is recorded and awaiting admin release.",
        kind="order",
    ))
    notify_admins(
        f"Client confirmed receipt of Order #{order.id} ('{order.artwork_title}'). The artist payout is ready for admin review.",
        "order",
    )
    db.session.commit()
    flash("Thank you! Order completed and the artist's net payout has been recorded for admin release.", "success")

    return redirect(url_for("order_status", token=order.token))


@app.route("/track", methods=["GET", "POST"])
@login_required
def track_order():
    if not current_user.is_admin and current_user.account_type != "client":
        abort(403)
    form = request.form
    if request.method == "POST":
        number = form.get("order_number", "").strip().lstrip("#")
        order = None
        if number.isdigit() and len(number) <= 9:
            if current_user.is_admin:
                order = db.session.get(Order, int(number))
            else:
                order = Order.query.filter_by(id=int(number), buyer_id=current_user.id).first()
                if order is None:
                    order = Order.query.filter_by(
                        id=int(number), buyer_id=None, buyer_email=current_user.email,
                    ).first()
                    if order:
                        order.buyer_id = current_user.id
                        db.session.commit()
        if order:
            return redirect(url_for("order_status", token=order.token))
        flash("We couldn’t find one of your orders with that number.", "error")
        return render_template("track.html", form=form), 400
    return render_template("track.html", form=form)


@app.route("/order/<token>")
@login_required
def order_status(token):
    order = Order.query.filter_by(token=token).first_or_404()
    if current_user.account_type != "client" and not current_user.is_admin and current_user.id != order.artist_id:
        abort(403)
    if order.buyer_id != current_user.id and not current_user.is_admin and current_user.id != order.artist_id:
        if order.buyer_id is None and order.buyer_email == current_user.email:
            order.buyer_id = current_user.id
            db.session.commit()
        else:
            abort(404)
            
    admin_user = Artist.query.filter_by(is_admin=True).first()
    admin_user_id = admin_user.id if admin_user else None

    return render_template("order_status.html", order=order, admin_user_id=admin_user_id)


@app.orders_route_stub if False else app.route("/orders")
@login_required
@artist_required
def orders():
    items = Order.query.filter_by(artist_id=current_user.id).order_by(Order.created_at.desc()).all()
    return render_template("orders.html", orders=items)


@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    form, errors = request.form, {}
    if request.method == "POST":
        action = form.get("action")
        if action == "email":
            new_email = form.get("new_email", "").strip().lower()
            if not check_password_hash(current_user.password_hash, form.get("email_password", "")):
                errors["email_password"] = "Incorrect password."
            if not EMAIL_RE.match(new_email):
                errors["new_email"] = "Enter a valid email address."
            elif new_email == current_user.email:
                errors["new_email"] = "That is already your email address."
            elif Artist.query.filter(db.func.lower(Artist.email) == new_email,
                                     Artist.id != current_user.id).first():
                errors["new_email"] = "This email is already in use."
            if not errors:
                current_user.email = new_email
                try:
                    db.session.commit()
                except IntegrityError:
                    db.session.rollback()
                    errors["new_email"] = "This email is already in use."
                else:
                    flash("Your email address has been updated.", "success")
                    return redirect(url_for("settings"))
        elif action == "password":
            new_password = form.get("new_password", "")
            if not check_password_hash(current_user.password_hash, form.get("current_password", "")):
                errors["current_password"] = "Incorrect password."
            if len(new_password) < 8:
                errors["new_password"] = "Password must be at least 8 characters."
            elif new_password != form.get("confirm_password", ""):
                errors["confirm_password"] = "Passwords do not match."
            if not errors:
                current_user.password_hash = generate_password_hash(new_password)
                db.session.commit()
                flash("Your password has been changed.", "success")
                return redirect(url_for("settings"))
        else:
            abort(400)
        flash("Please fix the highlighted fields.", "error")
        return render_template("settings.html", form=form, errors=errors), 400
    return render_template("settings.html", form=form, errors=errors)


@app.route("/privacy", methods=["GET", "POST"])
@login_required
@artist_required
def privacy():
    if request.method == "POST":
        current_user.show_in_directory = bool(request.form.get("show_in_directory"))
        current_user.show_member_since = bool(request.form.get("show_member_since"))
        db.session.commit()
        flash("Your privacy settings have been saved.", "success")
        return redirect(url_for("privacy"))
    return render_template("privacy.html")


@app.route("/notifications/preferences", methods=["POST"])
@login_required
@notifications_required
def notification_preferences():
    current_user.notify_new_orders = bool(request.form.get("notify_new_orders"))
    db.session.commit()
    flash("Your notification preferences have been saved.", "success")
    return redirect(url_for("notifications"))


@app.route("/notifications")
@login_required
@notifications_required
def notifications():
    items = (Notification.query.filter_by(artist_id=current_user.id)
             .order_by(Notification.created_at.desc()).limit(50).all())
    unread_ids = {n.id for n in items if not n.is_read}
    if unread_ids:
        Notification.query.filter(Notification.id.in_(unread_ids)).update(
            {"is_read": True}, synchronize_session=False)
        db.session.commit()
    return render_template("notifications.html", items=items, unread_ids=unread_ids)


@app.route("/notifications/clear", methods=["POST"])
@login_required
@notifications_required
def clear_notifications():
    Notification.query.filter_by(artist_id=current_user.id).delete()
    db.session.commit()
    flash("Notifications cleared.", "info")
    return redirect(url_for("notifications"))


# ==========================================
# 6. ADMIN PANEL ROUTES
# ==========================================

@app.route("/admin")
@admin_required
def admin_dashboard():
    stats = dict(
        artists=Artist.query.filter_by(account_type="artist", is_approved=True).count(),
        pending_artists=Artist.query.filter_by(
            account_type="artist", is_approved=False, suspended=False,
        ).count(),
        clients=Artist.query.filter_by(account_type="client").count(),
        suspended=Artist.query.filter_by(account_type="artist", suspended=True).count(),
        artworks=Artwork.query.count(),
        hidden=Artwork.query.filter_by(hidden=True).count(),
        sold=Artwork.query.filter_by(available=False).count(),
        orders=Order.query.count(),
        sales=db.session.query(db.func.coalesce(db.func.sum(Order.price), 0))
                .filter(Order.status == "completed").scalar(),
        funds_held=db.session.query(db.func.coalesce(db.func.sum(Order.price), 0))
                .filter(
                    Order.funds_received.is_(True),
                    Order.payout_released.is_(False),
                ).scalar(),
        payouts_pending=Order.query.filter(
            Order.status == "completed",
            Order.payout_recorded_at.is_not(None),
            Order.payout_released.is_(False),
        ).count(),
    )
    order_counts = {st: Order.query.filter_by(status=st).count()
                    for st in ("pending", "payment_uploaded", "in_escrow", "completed", "cancelled")}
    return render_template(
        "admin_dashboard.html", stats=stats, order_counts=order_counts,
        recent_orders=Order.query.order_by(Order.created_at.desc()).limit(5).all(),
    )


@app.route("/admin/artist-applications")
@admin_required
def admin_artist_applications():
    applicants = Artist.query.filter_by(
        account_type="artist", is_approved=False, suspended=False,
    ).order_by(Artist.created_at.asc()).all()
    return render_template("admin_artist_applications.html", applicants=applicants)


@app.route("/admin/artist-applications/<int:artist_id>/<action>", methods=["POST"])
@admin_required
def admin_artist_application_action(artist_id, action):
    applicant = db.get_or_404(Artist, artist_id)
    if applicant.account_type != "artist" or applicant.is_approved:
        abort(404)
    if action == "approve":
        applicant.is_approved = True
        applicant.show_in_directory = True
        message = f"{applicant.name} has been approved as an artist, and their custom style/medium and portfolio works are now live."
    elif action == "reject":
        applicant.account_type = "client"
        applicant.is_approved = False
        applicant.show_in_directory = False
        message = f"{applicant.name}'s application was declined; the account is now a client account."
    else:
        abort(404)
    db.session.commit()
    flash(message, "success")
    return redirect(url_for("admin_artist_applications"))


@app.route("/admin/artists")
@admin_required
def admin_artists():
    q = request.args.get("q", "").strip()
    query = Artist.query.filter_by(account_type="artist", is_admin=False)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Artist.name.ilike(like), Artist.email.ilike(like)))
    return render_template(
        "admin_artists.html", 
        q=q, 
        artists=query.order_by(Artist.created_at.desc()).all()
    )


@app.route("/admin/clients")
@admin_required
def admin_clients():
    q = request.args.get("q", "").strip()
    query = Artist.query.filter_by(account_type="client")
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Artist.name.ilike(like), Artist.email.ilike(like)))
    return render_template("admin_clients.html", q=q, clients=query.order_by(Artist.created_at.desc()).all())


@app.route("/admin/accounts/<int:account_id>/delete", methods=["POST"])
@admin_required
def admin_delete_account(account_id):
    account = db.get_or_404(Artist, account_id)
    if account.id == current_user.id:
        flash("You cannot delete your own account while logged in.", "error")
        return redirect(request.referrer or url_for("admin_dashboard"))
    acc_type = account.account_type
    db.session.delete(account)
    db.session.commit()
    flash(f"{account.name}'s account has been deleted.", "success")
    if acc_type == "client":
        return redirect(url_for("admin_clients"))
    return redirect(url_for("admin_artists"))


@app.route("/admin/artists/<int:artist_id>/<action>", methods=["POST"])
@admin_required
def admin_artist_action(artist_id, action):
    artist = db.get_or_404(Artist, artist_id)
    messages = {
        "suspend": f"{artist.name} has been suspended.",
        "activate": f"{artist.name} is active again.",
        "make-admin": f"{artist.name} is now an admin.",
        "remove-admin": f"{artist.name} is no longer an admin.",
    }
    if action not in messages:
        abort(404)
    if artist.id == current_user.id and action in ("suspend", "remove-admin"):
        flash("You can’t do that to your own account.", "error")
    elif action == "suspend" and artist.is_admin:
        flash("Remove admin rights first before suspending this account.", "error")
    else:
        if action == "suspend":
            artist.suspended = True
        elif action == "activate":
            artist.suspended = False
        elif action == "make-admin":
            artist.is_admin = True
            if artist.account_type == "artist":
                artist.is_approved = True
        else:
            artist.is_admin = False
        db.session.commit()
        flash(messages[action], "success")
    return redirect(request.referrer or url_for("admin_artists"))


@app.route("/admin/artworks")
@admin_required
def admin_artworks():
    return render_template("admin_artworks.html",
                           artworks=Artwork.query.order_by(Artwork.created_at.desc()).all())


@app.route("/admin/artworks/<int:artwork_id>/<action>", methods=["POST"])
@admin_required
def admin_artwork_action(artwork_id, action):
    artwork = db.get_or_404(Artwork, artwork_id)
    if action == "hide":
        artwork.hidden = True
        flash(f"“{artwork.title}” is now hidden from the public.", "success")
    elif action == "unhide":
        artwork.hidden = False
        flash(f"“{artwork.title}” is visible again and its custom categories are now live.", "success")
    elif action == "delete":
        if artwork.reserved:
            flash("This artwork has an active order. It can’t be deleted yet.", "error")
            return redirect(url_for("admin_artworks"))
        remove_image(artwork.image)
        db.session.delete(artwork)
        flash("Artwork deleted.", "success")
    else:
        abort(404)
    db.session.commit()
    return redirect(url_for("admin_artworks"))


@app.route("/admin/orders")
@admin_required
def admin_orders():
    orders = Order.query.order_by(Order.created_at.desc()).limit(200).all()
    held_orders = Order.query.filter(
        Order.funds_received.is_(True),
        Order.payout_released.is_(False),
    )
    funds_held = db.session.query(
        db.func.coalesce(db.func.sum(Order.price), 0)
    ).filter(
        Order.funds_received.is_(True),
        Order.payout_released.is_(False),
    ).scalar()
    payout_queue = Order.query.filter(
        Order.status == "completed",
        Order.payout_recorded_at.is_not(None),
        Order.payout_released.is_(False),
    ).count()
    return render_template(
        "admin_orders.html", orders=orders, funds_held=funds_held,
        held_order_count=held_orders.count(), payout_queue=payout_queue,
    )


@app.route("/admin/orders/<int:order_id>/release-payout", methods=["POST"])
@admin_required
def admin_release_payout(order_id):
    order = db.get_or_404(Order, order_id)
    if (
        order.status != "completed"
        or not order.funds_received
        or order.payout_recorded_at is None
        or order.payout_released
    ):
        flash("Only confirmed orders with verified escrow funds and a recorded payout can be released.", "error")
        return redirect(url_for("admin_orders"))

    now = datetime.now(timezone.utc)
    changed = Order.query.filter_by(
        id=order.id, status="completed", funds_received=True,
        payout_released=False,
    ).filter(
        Order.payout_recorded_at.is_not(None),
    ).update(
        {
            Order.payout_released: True,
            Order.payout_released_at: now,
        },
        synchronize_session=False,
    )
    if not changed:
        db.session.rollback()
        flash("This payout was already released or its status has changed.", "error")
        return redirect(url_for("admin_orders"))

    db.session.add(Notification(
        artist_id=order.artist_id,
        message=f"Admin recorded the release of your net payout of {order.payout_label} for Order #{order.id}.",
        kind="order",
    ))
    db.session.commit()
    flash(f"Net payout for Order #{order.id} recorded as released.", "success")
    return redirect(url_for("admin_orders"))


@app.route("/admin/manage-admins", methods=["GET", "POST"])
@admin_required
def admin_manage_admins():
    form = request.form
    errors = {}
    if request.method == "POST":
        name = form.get("name", "").strip()
        email = form.get("email", "").strip().lower()
        password = form.get("password", "")
        confirm = form.get("confirm", "")

        if not 2 <= len(name) <= 80:
            errors["name"] = "Enter a name between 2 and 80 characters."
        if not EMAIL_RE.match(email) or len(email) > 120:
            errors["email"] = "Enter a valid email address."
        elif Artist.query.filter(db.func.lower(Artist.email) == email).first():
            errors["email"] = "An account already uses this email address."
        if len(password) < 8:
            errors["password"] = "Password must be at least 8 characters."
        if password != confirm:
            errors["confirm"] = "Passwords do not match."

        if not errors:
            admin = Artist(
                name=name,
                email=email,
                password_hash=generate_password_hash(password),
                account_type="artist",
                is_approved=True,
                is_admin=True,
            )
            db.session.add(admin)
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                errors["email"] = "An account already uses this email address."
            else:
                flash(f"Admin account for {admin.name} has been created.", "success")
                return redirect(url_for("admin_manage_admins"))

    admins = Artist.query.filter_by(is_admin=True).order_by(Artist.created_at.desc()).all()
    return render_template(
        "admin_manage_admins.html", admins=admins, form=form, errors=errors,
    ), 400 if errors else 200


@app.route("/admin/delete-admin/<int:admin_id>", methods=["POST"])
@admin_required
def delete_admin_account(admin_id):
    target_admin = db.get_or_404(Artist, admin_id)
    if target_admin.id == current_user.id:
        flash("You cannot delete your own logged-in admin account.", "error")
        return redirect(url_for("admin_manage_admins"))
    if target_admin.is_admin:
        db.session.delete(target_admin)
        db.session.commit()
        flash(f"Admin account for {target_admin.name} has been permanently deleted.", "success")
    return redirect(url_for("admin_manage_admins"))


@app.route("/community/posts/<int:post_id>/edit", methods=["POST"])
@login_required
def edit_post(post_id):
    post = db.get_or_404(Post, post_id)
    if post.user_id != current_user.id:
        abort(403)
        
    caption = request.form.get("caption", "").strip()
    if len(caption) > 1000:
        flash("Caption must be 1,000 characters or fewer.", "error")
        return redirect(url_for("community"))
        
    post.caption = caption
    
    file = request.files.get("media")
    if file and file.filename:
        try:
            media_path, media_type = save_post_media(file)
            if post.media_path:
                remove_image(post.media_path)
            post.media_type = media_type
            post.media_path = media_path
        except ValueError as error:
            flash(str(error), "error")
            return redirect(url_for("community"))
            
    db.session.commit()
    flash("Your post has been updated.", "success")
    return redirect(url_for("community"))


# ==========================================
# 7. ERROR HANDLERS AT RUN CONFIGURATION
# ==========================================

@app.errorhandler(413)
def too_large(_e):
    flash("The image is too large. Maximum size is 5 MB.", "error")
    return redirect(url_for("profile" if request.endpoint == "profile" else "dashboard"))


@app.cli.command("create-admin")
@click.argument("email", default="")
@click.argument("password", default="")
def create_admin(email, password):
    with app.app_context():
        existing_admin = Artist.query.filter_by(email=email).first()
        if existing_admin:
            print(f"An account is already registered with this email: {email}")
            return
        hashed_password = generate_password_hash(password)
        admin = Artist(
            name="Admin ArtHub",
            email=email,
            password_hash=hashed_password,
            account_type="artist",
            is_approved=True,
            is_admin=True
        )
        db.session.add(admin)
        db.session.commit()
        print(f"Success! The admin account ({email}) has been created.")


if __name__ == "__main__":
    app.run(debug=True)