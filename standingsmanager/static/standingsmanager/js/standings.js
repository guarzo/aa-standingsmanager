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
    // Create alert container
    const alertDiv = $('<div>')
        .addClass('alert alert-success alert-dismissible fade in')
        .attr('role', 'alert');

    // Create close button
    const closeButton = $('<button>')
        .attr('type', 'button')
        .addClass('close')
        .attr('data-dismiss', 'alert')
        .attr('aria-label', 'Close')
        .append($('<span>').attr('aria-hidden', 'true').html('&times;'));

    // Create icon
    const icon = $('<i>').addClass('fas fa-check-circle');

    // Create message span and set text safely
    const messageSpan = $('<span>').text(' ' + message);

    // Assemble the alert
    alertDiv.append(closeButton).append(icon).append(messageSpan);

    // Insert after first h2
    $('h2').first().after(alertDiv);

    // Auto-dismiss after 5 seconds - use reference to specific alert
    setTimeout(function() {
        alertDiv.fadeOut('slow', function() {
            alertDiv.remove();
        });
    }, 5000);
}

// Show error message
function showError(message) {
    // Create alert container
    const alertDiv = $('<div>')
        .addClass('alert alert-danger alert-dismissible fade in')
        .attr('role', 'alert');

    // Create close button
    const closeButton = $('<button>')
        .attr('type', 'button')
        .addClass('close')
        .attr('data-dismiss', 'alert')
        .attr('aria-label', 'Close')
        .append($('<span>').attr('aria-hidden', 'true').html('&times;'));

    // Create icon
    const icon = $('<i>').addClass('fas fa-exclamation-circle');

    // Create message span and set text safely
    const messageSpan = $('<span>').text(' ' + message);

    // Assemble the alert
    alertDiv.append(closeButton).append(icon).append(messageSpan);

    // Insert after first h2
    $('h2').first().after(alertDiv);

    // Auto-dismiss after 10 seconds - use reference to specific alert
    setTimeout(function() {
        alertDiv.fadeOut('slow', function() {
            alertDiv.remove();
        });
    }, 10000);
}

// ============================================================================
// Bulk Selection Management
// ============================================================================

// Update bulk action button states
function updateBulkActionButtons() {
    const requestChecked = $('.request-checkbox:checked').length;
    const revokeChecked = $('.revoke-checkbox:checked').length;

    $('#request-count').text(requestChecked);
    $('#revoke-count').text(revokeChecked);

    $('#bulk-request-btn').prop('disabled', requestChecked === 0);
    $('#bulk-revoke-btn').prop('disabled', revokeChecked === 0);
}

// Select all checkbox handler
$(document).on('change', '#select-all-characters', function() {
    const isChecked = $(this).is(':checked');
    $('.character-checkbox').prop('checked', isChecked);
    updateBulkActionButtons();
});

// Individual checkbox handler
$(document).on('change', '.character-checkbox', function() {
    const totalCheckboxes = $('.character-checkbox').length;
    const checkedCheckboxes = $('.character-checkbox:checked').length;
    $('#select-all-characters').prop('checked', totalCheckboxes === checkedCheckboxes && totalCheckboxes > 0);
    updateBulkActionButtons();
});

// ============================================================================
// Bulk Request Characters
// ============================================================================
$(document).on('click', '#bulk-request-btn', function(e) {
    e.preventDefault();
    const button = $(this);
    const checkedBoxes = $('.request-checkbox:checked');
    const characterIds = [];
    const characterNames = [];

    checkedBoxes.each(function() {
        characterIds.push($(this).data('character-id'));
        characterNames.push($(this).data('character-name'));
    });

    if (characterIds.length === 0) {
        return;
    }

    const confirmMsg = characterIds.length === 1
        ? `Request standing for ${characterNames[0]}?`
        : `Request standings for ${characterIds.length} characters?\n\n${characterNames.join(', ')}`;

    if (!confirm(confirmMsg)) {
        return;
    }

    showLoading(button);

    $.ajax({
        url: '/standingsmanager/api/bulk-request-characters/',
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({ character_ids: characterIds }),
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
// Bulk Revoke Standings
// ============================================================================
$(document).on('click', '#bulk-revoke-btn', function(e) {
    e.preventDefault();
    const button = $(this);
    const checkedBoxes = $('.revoke-checkbox:checked');
    const entityIds = [];
    const entityNames = [];

    checkedBoxes.each(function() {
        entityIds.push($(this).data('entity-id'));
        entityNames.push($(this).data('entity-name'));
    });

    if (entityIds.length === 0) {
        return;
    }

    const confirmMsg = entityIds.length === 1
        ? `Request removal of standing for ${entityNames[0]}?\n\nAn approver will need to approve this request.`
        : `Request removal of standings for ${entityIds.length} characters?\n\n${entityNames.join(', ')}\n\nAn approver will need to approve these requests.`;

    if (!confirm(confirmMsg)) {
        return;
    }

    showLoading(button);

    $.ajax({
        url: '/standingsmanager/api/bulk-remove-standings/',
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({ entity_ids: entityIds }),
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
        url: `/standingsmanager/api/request-character/${characterId}/`,
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
        url: `/standingsmanager/api/request-corporation/${corporationId}/`,
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
        url: `/standingsmanager/api/remove-standing/${entityId}/`,
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
        url: `/standingsmanager/api/add-sync/${characterId}/`,
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
        url: `/standingsmanager/api/remove-sync/${syncedCharPk}/`,
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
        url: `/standingsmanager/api/approve-request/${requestPk}/`,
        method: 'POST',
        success: function(data) {
            showSuccess(data.message);
            // Remove row from table with animation
            row.fadeOut('slow', function() {
                $(this).remove();
                // Update badge count
                const badge = row.closest('.panel').find('.panel-title .badge');
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
        url: `/standingsmanager/api/reject-request/${requestPk}/`,
        method: 'POST',
        success: function(data) {
            showSuccess(data.message);
            // Remove row from table with animation
            row.fadeOut('slow', function() {
                $(this).remove();
                // Update badge count
                const badge = row.closest('.panel').find('.panel-title .badge');
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
        url: `/standingsmanager/api/approve-revocation/${revocationPk}/`,
        method: 'POST',
        success: function(data) {
            showSuccess(data.message);
            // Remove row from table with animation
            row.fadeOut('slow', function() {
                $(this).remove();
                // Update badge count
                const badge = row.closest('.panel').find('.panel-title .badge');
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
        url: `/standingsmanager/api/reject-revocation/${revocationPk}/`,
        method: 'POST',
        success: function(data) {
            showSuccess(data.message);
            // Remove row from table with animation
            row.fadeOut('slow', function() {
                $(this).remove();
                // Update badge count
                const badge = row.closest('.panel').find('.panel-title .badge');
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
