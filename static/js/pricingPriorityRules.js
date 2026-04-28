let pricingRules = [];
let draggedRuleId = null;
let isSaving = false;
let loadController = null;
const RULES_CACHE_KEY = 'admin_pricing_priority_rules_cache_v1';

const messageEl = document.getElementById('priority-message');
const listEl = document.getElementById('pricing-rule-list');
const saveButton = document.getElementById('save-rules-btn');
const reloadButton = document.getElementById('reload-rules-btn');

function setMessage(type, text) {
    if (!messageEl) {
        return;
    }

    if (!text) {
        messageEl.className = 'priority-message';
        messageEl.textContent = '';
        return;
    }

    messageEl.className = `priority-message is-visible is-${type}`;
    messageEl.textContent = text;
}

function setBusyState(busy) {
    isSaving = busy;
    if (saveButton) {
        saveButton.disabled = busy;
        saveButton.textContent = busy ? 'Saving...' : 'Save';
    }
    if (reloadButton) {
        reloadButton.disabled = busy;
    }
}

function normalizeRules(rules) {
    return (rules || []).map((rule, index) => ({
        PricingPriorityRuleId: Number(rule.PricingPriorityRuleId),
        RuleCode: rule.RuleCode || '',
        RuleName: rule.RuleName || '',
        PriorityNo: index + 1,
        IsEnabled: Number(rule.IsEnabled) === 1 ? 1 : 0,
    }));
}

function readRulesCache() {
    try {
        const raw = sessionStorage.getItem(RULES_CACHE_KEY);
        if (!raw) return null;
        const parsed = JSON.parse(raw);
        return Array.isArray(parsed) ? normalizeRules(parsed) : null;
    } catch (_) {
        return null;
    }
}

function writeRulesCache(rules) {
    try {
        sessionStorage.setItem(RULES_CACHE_KEY, JSON.stringify(normalizeRules(rules)));
    } catch (_) {
        // Best-effort cache only.
    }
}

function updatePriorityNumbers() {
    pricingRules = pricingRules.map((rule, index) => ({
        ...rule,
        PriorityNo: index + 1,
    }));
}

function moveRule(draggedId, targetId) {
    if (!draggedId || !targetId || draggedId === targetId) {
        return;
    }

    const draggedIndex = pricingRules.findIndex(rule => rule.PricingPriorityRuleId === draggedId);
    const targetIndex = pricingRules.findIndex(rule => rule.PricingPriorityRuleId === targetId);
    if (draggedIndex < 0 || targetIndex < 0) {
        return;
    }

    const [draggedRule] = pricingRules.splice(draggedIndex, 1);
    pricingRules.splice(targetIndex, 0, draggedRule);
    updatePriorityNumbers();
    renderRules();
}

function bindRowEvents(row, rule) {
    row.addEventListener('dragstart', event => {
        draggedRuleId = rule.PricingPriorityRuleId;
        row.classList.add('is-dragging');
        event.dataTransfer.effectAllowed = 'move';
        event.dataTransfer.setData('text/plain', String(rule.PricingPriorityRuleId));
    });

    row.addEventListener('dragend', () => {
        draggedRuleId = null;
        row.classList.remove('is-dragging');
        document.querySelectorAll('.priority-rule-row').forEach(item => item.classList.remove('drag-target'));
    });

    row.addEventListener('dragover', event => {
        event.preventDefault();
        event.dataTransfer.dropEffect = 'move';
        row.classList.add('drag-target');
    });

    row.addEventListener('dragleave', () => {
        row.classList.remove('drag-target');
    });

    row.addEventListener('drop', event => {
        event.preventDefault();
        row.classList.remove('drag-target');
        moveRule(draggedRuleId, rule.PricingPriorityRuleId);
    });
}

function renderRules() {
    if (!listEl) {
        return;
    }

    if (pricingRules.length === 0) {
        listEl.innerHTML = '<div class="priority-empty">No pricing priority rules found.</div>';
        return;
    }

    listEl.innerHTML = '';

    pricingRules.forEach(rule => {
        const row = document.createElement('div');
        row.className = 'priority-rule-row';
        row.draggable = true;
        row.dataset.ruleId = String(rule.PricingPriorityRuleId);
        row.innerHTML = `
            <div class="priority-number">
                <span class="drag-handle" title="Drag to reorder">⋮⋮</span>
                <span>${rule.PriorityNo}</span>
            </div>
            <div class="rule-details">
                <div class="rule-name">${rule.RuleName}</div>
                <div class="rule-code">${rule.RuleCode}</div>
            </div>
            <label class="rule-toggle">
                <input type="checkbox" ${rule.IsEnabled ? 'checked' : ''}>
                <span>${rule.IsEnabled ? 'Enabled' : 'Disabled'}</span>
            </label>
        `;

        const toggle = row.querySelector('input[type="checkbox"]');
        const toggleLabel = row.querySelector('.rule-toggle span');
        toggle.addEventListener('change', event => {
            rule.IsEnabled = event.target.checked ? 1 : 0;
            toggleLabel.textContent = rule.IsEnabled ? 'Enabled' : 'Disabled';
        });

        bindRowEvents(row, rule);
        listEl.appendChild(row);
    });
}

async function loadRules(showLoadingMessage = true) {
    setBusyState(false);
    const cached = readRulesCache();
    if (cached && cached.length) {
        pricingRules = cached;
        renderRules();
    } else if (showLoadingMessage) {
        setMessage('info', 'Loading pricing priority rules...');
        listEl.innerHTML = '<div class="priority-loading">Loading pricing priority rules...</div>';
    }

    try {
        if (loadController) {
            loadController.abort();
        }
        loadController = new AbortController();
        const response = await fetch('/api/admin/pricing-priority-rules', { signal: loadController.signal });
        const result = await response.json();
        if (!response.ok || !result.success) {
            throw new Error(result.error || result.message || 'Failed to load pricing priority rules');
        }

        pricingRules = normalizeRules(result.data);
        writeRulesCache(pricingRules);
        renderRules();
        if (showLoadingMessage) {
            setMessage('', '');
        }
    } catch (error) {
        if (error && error.name === 'AbortError') {
            return;
        }
        console.error('Failed to load pricing priority rules:', error);
        if (!pricingRules.length) {
            pricingRules = [];
            renderRules();
        }
        setMessage('error', error.message || 'Failed to load pricing priority rules');
    } finally {
        loadController = null;
    }
}

async function saveRules() {
    if (isSaving) {
        return;
    }

    updatePriorityNumbers();
    setBusyState(true);
    setMessage('info', 'Saving pricing priority rules...');

    try {
        const payload = {
            rules: pricingRules.map(rule => ({
                PricingPriorityRuleId: rule.PricingPriorityRuleId,
                PriorityNo: rule.PriorityNo,
                IsEnabled: rule.IsEnabled,
            })),
        };

        const response = await fetch('/api/admin/pricing-priority-rules/save', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(payload),
        });
        const result = await response.json();
        if (!response.ok || !result.success) {
            throw new Error(result.error || result.message || 'Failed to save pricing priority rules');
        }

        // Keep current UI order/toggles (already up to date) and avoid an extra round-trip reload.
        pricingRules = normalizeRules(pricingRules);
        writeRulesCache(pricingRules);
        renderRules();
        setMessage('success', result.message || 'Pricing priority rules saved successfully');
    } catch (error) {
        console.error('Failed to save pricing priority rules:', error);
        setMessage('error', error.message || 'Failed to save pricing priority rules');
    } finally {
        setBusyState(false);
    }
}

if (saveButton) {
    saveButton.addEventListener('click', saveRules);
}

if (reloadButton) {
    reloadButton.addEventListener('click', loadRules);
}

document.addEventListener('DOMContentLoaded', loadRules);
