/**
 * JavaScript for AA Standings Manager
 * Handles all AJAX operations for the standings system
 */

// Get CSRF token from cookies
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

const csrftoken = getCookie('csrftoken');

// Configure AJAX to include CSRF token
$.ajaxSetup({
    beforeSend: function(xhr, settings) {
        if (!(/^(GET|HEAD|OPTIONS|TRACE)$/.test(settings.type)) && !this.crossDomain) {
            xhr.setRequestHeader("X-CSRFToken", csrftoken);
        }
    }
});

// Show loading indicator
function showLoading(button) {
    const originalText = button.html();
    button.data('original-text', originalText);
    button.prop('disabled', true);
    button.html('<i class="fas fa-spinner fa-spin"></i> Processing...');
}

// Hide loading indicator
function hideLoading(button) {
    const originalText = button.data('original-text');
    button.prop('disabled', false);
    button.html(originalText);
}

// Show success message
function showSuccess(message) {
    const alertHtml = `
        <div class="alert alert-success alert-dismissible fade in" role="alert">
            <button type="button" class="close" data-dismiss="alert" aria-label="Close">
                <span aria-hidden="true">&times;</span>
            </button>
            <i class="fas fa-check-circle"></i> ${message}
        </div>
    `;
    $('h2').first().after(alertHtml);

    // Auto-dismiss after 5 seconds
    setTimeout(function() {
        $('.alert-success').fadeOut('slow', function() {
            $(this).remove();
        });
    }, 5000);
}

// Show error message
function showError(message) {
    const alertHtml = `
        <div class="alert alert-danger alert-dismissible fade in" role="alert">
            <button type="button" class="close" data-dismiss="alert" aria-label="Close">
                <span aria-hidden="true">&times;</span>
            </button>
            <i class="fas fa-exclamation-circle"></i> ${message}
        </div>
    `;
    $('h2').first().after(alertHtml);

    // Auto-dismiss after 10 seconds
    setTimeout(function() {
        $('.alert-danger').fadeOut('slow', function() {
            $(this).remove();
        });
    }, 10000);
}

// ============================================================================
// Request Character Standing
// ============================================================================
$(document).on('click', '.request-character-btn', function(e) {
    e.preventDefault();
    const button = $(this);
    const characterId = button.data('character-id');
    const characterName = button.data('character-name');

    if (!confirm(`Request standing for ${characterName}?`)) {
        return;
    }

    showLoading(button);

    $.ajax({
        url: `/standingssync/api/request-character/${characterId}/`,
        method: 'POST',
        success: function(data) {
            showSuccess(data.message);
            // Reload page after 1 second to show updated status
            setTimeout(function() {
                location.reload();
            }, 1000);
        },
        error: function(xhr) {
            hideLoading(button);
            const error = xhr.responseJSON ? xhr.responseJSON.error : 'An error occurred';
            showError(error);
        }
    });
});

// ============================================================================
// Request Corporation Standing
// ============================================================================
$(document).on('click', '.request-corporation-btn', function(e) {
    e.preventDefault();
    const button = $(this);
    const corporationId = button.data('corporation-id');
    const corporationName = button.data('corporation-name');

    if (!confirm(`Request standing for ${corporationName}?\n\nThis will request standings for the entire corporation.`)) {
        return;
    }

    showLoading(button);

    $.ajax({
        url: `/standingssync/api/request-corporation/${corporationId}/`,
        method: 'POST',
        success: function(data) {
            showSuccess(data.message);
            // Reload page after 1 second to show updated status
            setTimeout(function() {
                location.reload();
            }, 1000);
        },
        error: function(xhr) {
            hideLoading(button);
            const error = xhr.responseJSON ? xhr.responseJSON.error : 'An error occurred';
            showError(error);
        }
    });
});

// ============================================================================
// Remove Standing
// ============================================================================
$(document).on('click', '.remove-standing-btn', function(e) {
    e.preventDefault();
    const button = $(this);
    const entityId = button.data('entity-id');
    const entityName = button.data('entity-name');

    if (!confirm(`Request removal of standing for ${entityName}?\n\nAn approver will need to approve this request.`)) {
        return;
    }

    showLoading(button);

    $.ajax({
        url: `/standingssync/api/remove-standing/${entityId}/`,
        method: 'POST',
        success: function(data) {
            showSuccess(data.message);
            // Reload page after 1 second to show updated status
            setTimeout(function() {
                location.reload();
            }, 1000);
        },
        error: function(xhr) {
            hideLoading(button);
            const error = xhr.responseJSON ? xhr.responseJSON.error : 'An error occurred';
            showError(error);
        }
    });
});

// ============================================================================
// Add Character to Sync
// ============================================================================
$(document).on('click', '.add-sync-btn', function(e) {
    e.preventDefault();
    const button = $(this);
    const characterId = button.data('character-id');
    const characterName = button.data('character-name');

    if (!confirm(`Add ${characterName} to sync?\n\nMake sure you've created the required contact label in-game!`)) {
        return;
    }

    showLoading(button);

    $.ajax({
        url: `/standingssync/api/add-sync/${characterId}/`,
        method: 'POST',
        success: function(data) {
            showSuccess(data.message);
            // Reload page after 1 second to show updated status
            setTimeout(function() {
                location.reload();
            }, 1000);
        },
        error: function(xhr) {
            hideLoading(button);
            const error = xhr.responseJSON ? xhr.responseJSON.error : 'An error occurred';
            showError(error);
        }
    });
});

// ============================================================================
// Remove Character from Sync
// ============================================================================
$(document).on('click', '.remove-sync-btn', function(e) {
    e.preventDefault();
    const button = $(this);
    const syncedCharPk = button.data('synced-char-pk');
    const characterName = button.data('character-name');

    if (!confirm(`Remove ${characterName} from sync?\n\nStandings will no longer be automatically synced for this character.`)) {
        return;
    }

    showLoading(button);

    $.ajax({
        url: `/standingssync/api/remove-sync/${syncedCharPk}/`,
        method: 'POST',
        success: function(data) {
            showSuccess(data.message);
            // Reload page after 1 second to show updated status
            setTimeout(function() {
                location.reload();
            }, 1000);
        },
        error: function(xhr) {
            hideLoading(button);
            const error = xhr.responseJSON ? xhr.responseJSON.error : 'An error occurred';
            showError(error);
        }
    });
});

// ============================================================================
// Approve Standing Request
// ============================================================================
$(document).on('click', '.approve-request-btn', function(e) {
    e.preventDefault();
    const button = $(this);
    const requestPk = button.data('request-pk');
    const entityName = button.data('entity-name');
    const row = $(`#request-row-${requestPk}`);

    if (!confirm(`Approve standing request for ${entityName}?\n\nThis will create a standings entry and trigger sync for all synced characters.`)) {
        return;
    }

    showLoading(button);

    $.ajax({
        url: `/standingssync/api/approve-request/${requestPk}/`,
        method: 'POST',
        success: function(data) {
            showSuccess(data.message);
            // Remove row from table with animation
            row.fadeOut('slow', function() {
                $(this).remove();
                // Update badge count
                const badge = $('.panel-title .badge');
                const currentCount = parseInt(badge.text());
                badge.text(currentCount - 1);
            });
        },
        error: function(xhr) {
            hideLoading(button);
            const error = xhr.responseJSON ? xhr.responseJSON.error : 'An error occurred';
            showError(error);
        }
    });
});

// ============================================================================
// Reject Standing Request
// ============================================================================
$(document).on('click', '.reject-request-btn', function(e) {
    e.preventDefault();
    const button = $(this);
    const requestPk = button.data('request-pk');
    const entityName = button.data('entity-name');
    const row = $(`#request-row-${requestPk}`);

    if (!confirm(`Reject standing request for ${entityName}?\n\nThis will delete the request and notify the requester.`)) {
        return;
    }

    showLoading(button);

    $.ajax({
        url: `/standingssync/api/reject-request/${requestPk}/`,
        method: 'POST',
        success: function(data) {
            showSuccess(data.message);
            // Remove row from table with animation
            row.fadeOut('slow', function() {
                $(this).remove();
                // Update badge count
                const badge = $('.panel-title .badge');
                const currentCount = parseInt(badge.text());
                badge.text(currentCount - 1);
            });
        },
        error: function(xhr) {
            hideLoading(button);
            const error = xhr.responseJSON ? xhr.responseJSON.error : 'An error occurred';
            showError(error);
        }
    });
});

// ============================================================================
// Approve Standing Revocation
// ============================================================================
$(document).on('click', '.approve-revocation-btn', function(e) {
    e.preventDefault();
    const button = $(this);
    const revocationPk = button.data('revocation-pk');
    const entityName = button.data('entity-name');
    const row = $(`#revocation-row-${revocationPk}`);

    if (!confirm(`Approve standing removal for ${entityName}?\n\nThis will permanently delete the standings entry and trigger sync for all synced characters.`)) {
        return;
    }

    showLoading(button);

    $.ajax({
        url: `/standingssync/api/approve-revocation/${revocationPk}/`,
        method: 'POST',
        success: function(data) {
            showSuccess(data.message);
            // Remove row from table with animation
            row.fadeOut('slow', function() {
                $(this).remove();
                // Update badge count
                const badge = $('.panel-title .badge');
                const currentCount = parseInt(badge.text());
                badge.text(currentCount - 1);
            });
        },
        error: function(xhr) {
            hideLoading(button);
            const error = xhr.responseJSON ? xhr.responseJSON.error : 'An error occurred';
            showError(error);
        }
    });
});

// ============================================================================
// Reject Standing Revocation
// ============================================================================
$(document).on('click', '.reject-revocation-btn', function(e) {
    e.preventDefault();
    const button = $(this);
    const revocationPk = button.data('revocation-pk');
    const entityName = button.data('entity-name');
    const row = $(`#revocation-row-${revocationPk}`);

    if (!confirm(`Reject standing removal for ${entityName}?\n\nThis will keep the standings entry and delete the revocation request.`)) {
        return;
    }

    showLoading(button);

    $.ajax({
        url: `/standingssync/api/reject-revocation/${revocationPk}/`,
        method: 'POST',
        success: function(data) {
            showSuccess(data.message);
            // Remove row from table with animation
            row.fadeOut('slow', function() {
                $(this).remove();
                // Update badge count
                const badge = $('.panel-title .badge');
                const currentCount = parseInt(badge.text());
                badge.text(currentCount - 1);
            });
        },
        error: function(xhr) {
            hideLoading(button);
            const error = xhr.responseJSON ? xhr.responseJSON.error : 'An error occurred';
            showError(error);
        }
    });
});
