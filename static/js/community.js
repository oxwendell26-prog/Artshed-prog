/**
 * COMMUNITY FEED INTERACTION ENGINE
 * Pamamahala sa AJAX posting, reactions, comments, editing, at lightboxes ng community feed
 */

let currentEditingPostId = null;

function openImageViewer(event, src) {
    if (event) event.preventDefault();
    if (!src) return;
    document.getElementById('fullSizeImage').src = src;
    document.getElementById('imageViewerModal').classList.remove('hidden');
}

function closeImageViewer(event) {
    if (event) event.preventDefault();
    document.getElementById('imageViewerModal').classList.add('hidden');
}

function openEditModalFromBtn(event, btn) {
    if (event) event.preventDefault();
    currentEditingPostId = btn.getAttribute('data-post-id');
    const caption = btn.getAttribute('data-caption');

    document.getElementById('editCaption').value = caption;
    document.getElementById('editPostForm').action = "/community/posts/" + currentEditingPostId + "/edit";
    document.getElementById('editPostModal').classList.remove('hidden');
}

function closeEditModal(event) {
    if (event) event.preventDefault();
    document.getElementById('editPostModal').classList.add('hidden');
    currentEditingPostId = null;
}

function openEditCommentModal(commentId, content) {
    document.getElementById('editCommentContent').value = content;
    document.getElementById('editCommentForm').action = "/community/comments/" + commentId + "/edit";
    document.getElementById('editCommentModal').classList.remove('hidden');
}

function closeEditCommentModal() {
    document.getElementById('editCommentModal').classList.add('hidden');
}

// AJAX para sa Reactions (Like / Heart)
async function reactPostAjax(event, postId, reactionType, url, csrfToken) {
    if (event) event.preventDefault();

    try {
        const formData = new FormData();
        formData.append('csrf_token', csrfToken);

        const response = await fetch(url, {
            method: 'POST',
            body: formData,
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        });

        if (response.ok) {
            const data = await response.json();

            // Update counts
            document.getElementById('count-like-' + postId).textContent = '(' + data.like_count + ')';
            document.getElementById('count-heart-' + postId).textContent = '(' + data.heart_count + ')';

            const btnLike = document.getElementById('btn-like-' + postId);
            const btnHeart = document.getElementById('btn-heart-' + postId);

            // Update active styles gamit ang ating mga bagong CSS classes
            btnLike.className = "community-reaction-btn " + (data.user_reaction === 'like' ? 'liked' : '');
            btnHeart.className = "community-reaction-btn " + (data.user_reaction === 'heart' ? 'hearted' : '');
        }
    } catch (error) {
        console.error('Error:', error);
    }
}

// AJAX para sa pagdaragdag ng Comment
async function addCommentAjax(event, postId, actionUrl) {
    event.preventDefault();
    const form = event.target;
    const formData = new FormData(form);

    try {
        const response = await fetch(actionUrl, {
            method: 'POST',
            body: formData,
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        });

        if (response.ok) {
            const data = await response.json();
            if (data.success) {
                const commentsList = document.getElementById('comments-list-' + postId);

                // Gumawa ng HTML structure para sa bagong comment
                const commentDiv = document.createElement('div');
                commentDiv.id = 'comment-item-' + data.comment_id;
                commentDiv.className = 'community-comment-item';

                const avatarHtml = data.user_avatar
                    ? `<img src="/static/uploads/${data.user_avatar}" class="h-7 w-7 rounded-full object-cover">`
                    : `<div class="h-7 w-7 rounded-full bg-neutral-800 flex items-center justify-center text-xs font-semibold text-brass">${data.user_initials}</div>`;

                commentDiv.innerHTML = `
          <div class="flex items-start gap-2.5">
            ${avatarHtml}
            <div>
              <span class="community-comment-username">${data.user_name}</span>
              <p class="community-comment-content">${data.content}</p>
            </div>
          </div>
          <div class="flex items-center gap-1 text-xs shrink-0">
            <button type="button" onclick="openEditCommentModal('${data.comment_id}', ${JSON.stringify(data.content)})" class="community-comment-btn-edit">Edit</button>
            <button type="button" onclick="deleteCommentAjax('${data.comment_id}', '/community/comments/${data.comment_id}/delete', '${formData.get('csrf_token')}')" class="community-comment-btn-delete">Delete</button>
          </div>
        `;

                commentsList.appendChild(commentDiv);
                document.getElementById('comment-input-' + postId).value = '';
            }
        }
    } catch (error) {
        console.error('Error:', error);
    }
}

async function submitEditPost(event) {
    event.preventDefault();
    const form = document.getElementById('editPostForm');
    const formData = new FormData(form);
    const actionUrl = form.action;

    try {
        const response = await fetch(actionUrl, {
            method: 'POST',
            body: formData,
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        });

        if (response.ok) {
            const newCaption = document.getElementById('editCaption').value;
            const captionContainer = document.getElementById('post-caption-container-' + currentEditingPostId);

            if (newCaption.trim() !== '') {
                let textP = document.getElementById('post-caption-text-' + currentEditingPostId);
                if (!textP) {
                    textP = document.createElement('p');
                    textP.id = 'post-caption-text-' + currentEditingPostId;
                    textP.className = "community-post-caption";
                    captionContainer.appendChild(textP);
                }
                textP.textContent = newCaption;
            } else {
                captionContainer.innerHTML = '';
            }

            const editBtn = document.querySelector(`button[data-post-id="${currentEditingPostId}"]`);
            if (editBtn) {
                editBtn.setAttribute('data-caption', newCaption);
            }

            closeEditModal();
            window.location.reload();
        } else {
            alert('May nangyaring mali sa pag-update ng post.');
        }
    } catch (error) {
        console.error('Error:', error);
        alert('Hindi makakonekta sa server.');
    }
}

async function deletePostAjax(postId, deleteUrl, csrfToken) {
    if (!confirm('Sigurado ka bang gusto mong burahin ang post na ito?')) {
        return;
    }

    try {
        const formData = new FormData();
        formData.append('csrf_token', csrfToken);

        const response = await fetch(deleteUrl, {
            method: 'POST',
            body: formData,
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        });

        if (response.ok) {
            const articleElement = document.getElementById('post-article-' + postId);
            if (articleElement) {
                articleElement.remove();
            }
        } else {
            alert('Hindi mabura ang post.');
        }
    } catch (error) {
        console.error('Error:', error);
        alert('May error sa koneksyon.');
    }
}

async function deleteCommentAjax(commentId, deleteUrl, csrfToken) {
    if (!confirm('Sigurado ka bang gusto mong burahin ang comment na ito?')) {
        return;
    }

    try {
        const formData = new FormData();
        formData.append('csrf_token', csrfToken);

        const response = await fetch(deleteUrl, {
            method: 'POST',
            body: formData,
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        });

        if (response.ok) {
            const commentElement = document.getElementById('comment-item-' + commentId);
            if (commentElement) {
                commentElement.remove();
            }
        } else {
            alert('Hindi mabura ang comment.');
        }
    } catch (error) {
        console.error('Error:', error);
        alert('May error sa koneksyon.');
    }
}