// ===========================================================================
// AI Scorecard Builder - Frontend
// ===========================================================================

let uploadedFilename = null;
let csvColumns = [];
let csvNumericColumns = [];
let csvCategoricalColumns = [];
let csvDateColumns = [];
let productCategories = [];

let metricsGridApi = null;
let columnsGridApi = null;
let previewGridApi = null;
let currentScorecardData = null;
let currentAbortController = null;

async function parseErrorResponse(resp) {
    try {
        const text = await resp.text();
        return JSON.parse(text);
    } catch {
        return { detail: 'Server error (non-JSON response). Check server logs.' };
    }
}

// ---------------------------------------------------------------------------
// AG Grid helpers
// ---------------------------------------------------------------------------

const AG_GRID_OPTS = {
    rowSelection: 'single',
    animateRows: true,
    defaultColDef: {
        resizable: true,
        sortable: false,
        filter: false,
    },
};

// ---------------------------------------------------------------------------
// CSV Upload
// ---------------------------------------------------------------------------

const uploadArea = document.getElementById('upload-area');
const fileInput = document.getElementById('csv-file-input');
const uploadPrompt = document.getElementById('upload-prompt');
const uploadSuccess = document.getElementById('upload-success');

uploadArea.addEventListener('click', () => fileInput.click());

uploadArea.addEventListener('dragover', (e) => {
    e.preventDefault();
    uploadArea.classList.add('dragover');
});

uploadArea.addEventListener('dragleave', () => uploadArea.classList.remove('dragover'));

uploadArea.addEventListener('drop', (e) => {
    e.preventDefault();
    uploadArea.classList.remove('dragover');
    if (e.dataTransfer.files.length) handleFile(e.dataTransfer.files[0]);
});

fileInput.addEventListener('change', () => {
    if (fileInput.files.length) handleFile(fileInput.files[0]);
});

async function handleFile(file) {
    if (!file.name.endsWith('.csv')) {
        alert('Please upload a CSV file.');
        return;
    }

    showLoading('Uploading CSV...');
    const formData = new FormData();
    formData.append('file', file);

    try {
        const resp = await fetch('/api/upload-csv', { method: 'POST', body: formData });
        if (!resp.ok) {
            const err = await parseErrorResponse(resp);
            throw new Error(err.detail || 'Upload failed');
        }
        const data = await resp.json();

        uploadedFilename = data.filename;
        csvColumns = data.columns.map(c => c.name);
        csvNumericColumns = data.numeric_columns;
        csvCategoricalColumns = data.categorical_columns;
        csvDateColumns = data.date_columns;
        productCategories = data.product_categories || [];

        // Update UI
        uploadPrompt.style.display = 'none';
        uploadSuccess.style.display = 'flex';
        document.getElementById('uploaded-filename').textContent = data.filename;
        document.getElementById('uploaded-info').textContent =
            `${data.row_count.toLocaleString()} rows × ${data.columns.length} columns`;

        // Show config step
        document.getElementById('step-configure').style.display = 'block';

        // Populate group-by dropdown
        populateGroupByDropdown();

        // Load preview
        await loadPreview(data.filename);

    } catch (err) {
        alert('Error: ' + err.message);
    } finally {
        hideLoading();
    }
}

function populateGroupByDropdown() {
    const sel = document.getElementById('group-by-select');
    sel.innerHTML = '';
    csvCategoricalColumns.forEach(col => {
        const opt = document.createElement('option');
        opt.value = col;
        opt.textContent = col;
        sel.appendChild(opt);
    });
    // Default to Region if available
    if (csvCategoricalColumns.includes('Region')) {
        sel.value = 'Region';
    }
}

// ---------------------------------------------------------------------------
// CSV Preview
// ---------------------------------------------------------------------------

async function loadPreview(filename) {
    try {
        const resp = await fetch(`/api/preview-csv/${filename}`);
        const data = await resp.json();
        document.getElementById('csv-preview-container').style.display = 'block';

        const colDefs = data.columns.map(col => ({
            headerName: col,
            field: col,
            flex: 1,
            minWidth: 100,
        }));

        const gridOptions = {
            ...AG_GRID_OPTS,
            columnDefs: colDefs,
            rowData: data.rows,
        };

        const container = document.getElementById('csv-preview-grid');
        container.innerHTML = '';
        previewGridApi = agGrid.createGrid(container, gridOptions);
    } catch (err) {
        console.error('Preview load error:', err);
    }
}

// ---------------------------------------------------------------------------
// Metrics Grid (Scorecard Rows)
// ---------------------------------------------------------------------------

function initMetricsGrid() {
    const colDefs = [
        {
            headerName: 'Section',
            field: 'section',
            width: 100,
            editable: true,
            cellEditor: 'agSelectCellEditor',
            cellEditorParams: {
                values: ['RUM', 'Buyers', 'Products', 'Custom'],
            },
        },
        {
            headerName: 'Metric Name',
            field: 'name',
            width: 180,
            editable: true,
        },
        {
            headerName: 'Data Column',
            field: 'data_column',
            width: 160,
            editable: true,
            cellEditor: 'agSelectCellEditor',
            cellEditorParams: () => ({
                values: ['', ...csvColumns],
            }),
        },
        {
            headerName: 'Aggregation',
            field: 'aggregation',
            width: 110,
            editable: true,
            cellEditor: 'agSelectCellEditor',
            cellEditorParams: {
                values: ['sum', 'mean', 'count', 'nunique', 'min', 'max', 'custom'],
            },
        },
        {
            headerName: 'Formula',
            field: 'formula',
            width: 220,
            editable: true,
        },
        {
            headerName: 'Product Filter',
            field: 'product_filter',
            width: 140,
            editable: true,
            cellEditor: 'agSelectCellEditor',
            cellEditorParams: () => ({
                values: ['', ...productCategories],
            }),
        },
        {
            headerName: 'Comparison',
            field: 'comparison',
            width: 110,
            editable: true,
            cellEditor: 'agSelectCellEditor',
            cellEditorParams: {
                values: ['', 'Q/Q', 'Y/Y', 'bps'],
            },
        },
        {
            headerName: 'Base Metric',
            field: 'base_metric',
            width: 160,
            editable: true,
        },
        {
            headerName: 'Previous Value',
            field: 'comparison_value',
            width: 130,
            editable: true,
            tooltipText: 'Previous period value for % change calculation (e.g. 8200000 for Q1 revenue)',
        },
    ];

    const gridOptions = {
        ...AG_GRID_OPTS,
        columnDefs: colDefs,
        rowData: [],
        onCellValueChanged: (event) => {
            // Auto-fill base_metric when comparison is set
            if (event.colDef.field === 'comparison' && event.newValue) {
                const row = event.data;
                if (!row.base_metric) {
                    // Try to find the corresponding base metric
                    const sectionRows = metricsGridApi.getModel().rowsData
                        .filter(r => r.section === row.section && r.name !== row.name && !r.comparison);
                    if (sectionRows.length > 0) {
                        const baseRow = sectionRows.find(r => r.name.includes(row.name.replace(/\s*(Q\/Q|Y\/Y|bps)\s*/, '')));
                        if (baseRow) {
                            metricsGridApi.applyTransaction({ update: [{ ...row, base_metric: baseRow.name }] });
                        }
                    }
                }
            }
        },
    };

    const container = document.getElementById('metrics-grid');
    container.innerHTML = '';
    metricsGridApi = agGrid.createGrid(container, gridOptions);
}

// ---------------------------------------------------------------------------
// Columns Grid (Scorecard Columns / Dimension Values)
// ---------------------------------------------------------------------------

function initColumnsGrid() {
    const colDefs = [
        {
            headerName: 'Column Name',
            field: 'name',
            width: 250,
            editable: true,
        },
        {
            headerName: 'Filter Value',
            field: 'filter_value',
            width: 250,
            editable: true,
            tooltipText: 'Optional: filter the data to only this value for this column',
        },
    ];

    const gridOptions = {
        ...AG_GRID_OPTS,
        columnDefs: colDefs,
        rowData: [],
    };

    const container = document.getElementById('columns-grid');
    container.innerHTML = '';
    columnsGridApi = agGrid.createGrid(container, gridOptions);
}

// ---------------------------------------------------------------------------
// Add / Remove rows
// ---------------------------------------------------------------------------

document.getElementById('btn-add-metric').addEventListener('click', () => {
    const section = document.getElementById('section-select').value || 'RUM';
    metricsGridApi.applyTransaction({
        add: [{ section, name: '', data_column: '', aggregation: 'sum', formula: '', product_filter: '', comparison: '', base_metric: '', comparison_value: '' }],
    });
});

document.getElementById('btn-remove-metric').addEventListener('click', () => {
    const selected = metricsGridApi.getSelectedRows();
    if (selected.length) {
        metricsGridApi.applyTransaction({ remove: selected });
    }
});

document.getElementById('btn-add-column').addEventListener('click', () => {
    columnsGridApi.applyTransaction({
        add: [{ name: '', filter_value: '' }],
    });
});

document.getElementById('btn-remove-column').addEventListener('click', () => {
    const selected = columnsGridApi.getSelectedRows();
    if (selected.length) {
        columnsGridApi.applyTransaction({ remove: selected });
    }
});

// ---------------------------------------------------------------------------
// Calculate Scorecard
// ---------------------------------------------------------------------------

document.getElementById('btn-calculate-direct').addEventListener('click', () => calculateScorecard(false));
document.getElementById('btn-calculate').addEventListener('click', () => calculateScorecard(true));

async function calculateScorecard(useLLM) {
    if (!uploadedFilename) {
        alert('Please upload a CSV first.');
        return;
    }

    const rows = [];
    metricsGridApi.forEachNode(node => rows.push(node.data));
    const columns = [];
    columnsGridApi.forEachNode(node => columns.push(node.data));

    if (!rows.length || !columns.length) {
        alert('Please add at least one metric row and one scorecard column.');
        return;
    }

    const emptyMetrics = rows.filter(r => !r.name || !r.data_column);
    if (emptyMetrics.length > 0) {
        if (!confirm(`${emptyMetrics.length} row(s) have empty Metric Name or Data Column and will produce no results. Continue anyway?`)) {
            return;
        }
    }

    const payload = {
        csv_filename: uploadedFilename,
        rows: rows,
        columns: columns,
        group_by: document.getElementById('group-by-select').value,
    };

    if (useLLM) {
        // Multi-step: Plan (LLM) → Calculate (pandas) → Validate (LLM)
        const signal = startOperation();
        try {
            // Step 1: Plan — LLM enriches rows with data_column, aggregation, formulas
            showLoading('Step 1/3: LLM is analyzing dataset and planning metrics...');
            let enrichedRows = rows;
            try {
                const planResp = await fetch('/api/llm/plan', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        csv_filename: uploadedFilename,
                        rows: rows,
                        columns: columns,
                        group_by: document.getElementById('group-by-select').value,
                        rules: document.getElementById('rules-input').value.trim(),
                    }),
                    signal,
                });
                if (planResp.ok) {
                    const planData = await planResp.json();
                    if (planData.plan && planData.plan.rows && planData.plan.rows.length > 0) {
                        enrichedRows = planData.plan.rows;
                        metricsGridApi.setGridOption('rowData', enrichedRows);
                    }
                } else {
                    console.warn('Plan step failed, using current grid rows');
                }
            } catch (planErr) {
                if (isAbortError(planErr)) throw planErr;
                console.warn('Plan step error (non-fatal):', planErr);
            }

            // Step 2: Calculate with pandas
            showLoading('Step 2/3: Calculating scorecard with pandas...');
            const calcPayload = {
                csv_filename: uploadedFilename,
                rows: enrichedRows,
                columns: columns,
                group_by: document.getElementById('group-by-select').value,
            };
            const calcResp = await fetch('/api/calculate-direct', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(calcPayload),
                signal,
            });
            if (!calcResp.ok) {
                const err = await parseErrorResponse(calcResp);
                throw new Error(err.detail || 'Calculation failed');
            }
            currentScorecardData = await calcResp.json();
            renderScorecard(currentScorecardData, columns);
            document.getElementById('step-results').style.display = 'block';

            // Step 3: Validate with LLM
            showLoading('Step 3/3: LLM is validating results for anomalies...');
            try {
                const valBody = {
                    scorecard_def: { rows: enrichedRows, columns },
                    results: currentScorecardData,
                    rules: document.getElementById('rules-input').value.trim(),
                };
                const valResp = await fetch('/api/llm/validate', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(valBody),
                    signal,
                });
                if (valResp.ok) {
                    const valData = await valResp.json();
                    renderValidationReport(valData.validation);
                }
            } catch (valErr) {
                if (isAbortError(valErr)) throw valErr;
                console.error('Validation failed (non-fatal):', valErr);
            }

            document.getElementById('step-results').scrollIntoView({ behavior: 'smooth' });
        } catch (err) {
            if (isAbortError(err)) {
                // User cancelled — already showed results from step 2 if available
            } else {
                alert('Error: ' + err.message);
            }
        } finally {
            hideLoading();
        }
    } else {
        // Direct: pandas only, no LLM
        const signal = startOperation();
        showLoading('Calculating...');
        try {
            const resp = await fetch('/api/calculate-direct', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
                signal,
            });
            if (!resp.ok) {
                const err = await parseErrorResponse(resp);
                throw new Error(err.detail || 'Calculation failed');
            }
            currentScorecardData = await resp.json();
            renderScorecard(currentScorecardData, columns);
            document.getElementById('step-results').style.display = 'block';
            document.getElementById('step-results').scrollIntoView({ behavior: 'smooth' });
        } catch (err) {
            if (!isAbortError(err)) {
                alert('Error: ' + err.message);
            }
        } finally {
            hideLoading();
        }
    }
}

// ---------------------------------------------------------------------------
// Render Scorecard
// ---------------------------------------------------------------------------

function renderScorecard(data, columnDefs) {
    const container = document.getElementById('scorecard-display');
    const colNames = columnDefs.map(c => c.name);
    const sections = data.sections || [];

    let html = '<table class="scorecard-table">';

    // Header row
    html += '<thead><tr>';
    html += '<th style="background:#1a1a2e; width:40px;"></th>';
    html += '<th style="background:#1a1a2e; text-align:left; min-width:200px;">Metric</th>';
    colNames.forEach(name => {
        html += `<th>${name}</th>`;
    });
    html += '</tr></thead>';

    // Body
    html += '<tbody>';
    let currentSection = null;
    let sectionIndex = 0;
    const totalCols = colNames.length + 2; // metric-name + section-label + value cols

    data.results.forEach(result => {
        if (result.section !== currentSection) {
            if (currentSection !== null) {
                sectionIndex++;
            }
            currentSection = result.section;

            // Add separator row between sections (not before first)
            if (sectionIndex > 0) {
                html += `<tr><td class="section-separator" colspan="${totalCols}"></td></tr>`;
            }

            html += `<tr><td class="section-label" rowspan="${countSectionRows(data.results, currentSection)}">${currentSection}</td>`;
        }

        const isFirstInSection = data.results.indexOf(result) ===
            data.results.findIndex(r => r.section === currentSection);

        if (!isFirstInSection) html += '<tr>';

        html += `<td class="metric-name">${result.metric}</td>`;
        colNames.forEach(col => {
            const val = result.values[col];
            const formatted = formatValue(val, result.metric, result.comparison);
            const cls = getValClass(val);
            html += `<td class="value ${cls}">${formatted}</td>`;
        });
        html += '</tr>';
    });

    html += '</tbody></table>';
    container.innerHTML = html;
}

function countSectionRows(results, section) {
    return results.filter(r => r.section === section).length;
}

function formatValue(val, metric, comparison) {
    if (val === null || val === undefined) return '-';
    if (typeof val === 'number') {
        if (metric && (metric.includes('%') || metric.includes('GM%'))) {
            return val.toFixed(2) + '%';
        }
        if (comparison) {
            return (val >= 0 ? '+' : '') + val.toFixed(2) + '%';
        }
        if (Math.abs(val) >= 1000000) return (val / 1000000).toFixed(1) + 'M';
        if (Math.abs(val) >= 1000) return (val / 1000).toFixed(1) + 'K';
        return val.toLocaleString(undefined, { maximumFractionDigits: 2 });
    }
    return String(val);
}

function getValClass(val) {
    if (typeof val !== 'number') return '';
    return val >= 0 ? 'positive' : 'negative';
}

// ---------------------------------------------------------------------------
// Export
// ---------------------------------------------------------------------------

document.getElementById('btn-export-excel').addEventListener('click', () => exportScorecard('excel'));
document.getElementById('btn-export-csv').addEventListener('click', () => exportScorecard('csv'));

async function exportScorecard(format) {
    if (!uploadedFilename || !currentScorecardData) return;

    const rows = [];
    metricsGridApi.forEachNode(node => rows.push(node.data));
    const columns = [];
    columnsGridApi.forEachNode(node => columns.push(node.data));

    const payload = {
        csv_filename: uploadedFilename,
        rows: rows,
        columns: columns,
        group_by: document.getElementById('group-by-select').value,
    };

    showLoading('Exporting...');

    try {
        const resp = await fetch(`/api/export/${format}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });

        if (!resp.ok) throw new Error('Export failed');

        const blob = await resp.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `scorecard.${format === 'excel' ? 'xlsx' : 'csv'}`;
        a.click();
        URL.revokeObjectURL(url);
    } catch (err) {
        alert('Export error: ' + err.message);
    } finally {
        hideLoading();
    }
}

// ---------------------------------------------------------------------------
// Templates
// ---------------------------------------------------------------------------

document.getElementById('btn-load-template').addEventListener('click', loadTemplates);
document.getElementById('modal-close').addEventListener('click', () => {
    document.getElementById('template-modal').style.display = 'none';
});

async function loadTemplates() {
    try {
        const resp = await fetch('/api/templates');
        const templates = await resp.json();

        const list = document.getElementById('template-list');
        if (templates.length === 0) {
            list.innerHTML = '<p style="color:#6b7280">No templates found. Save one first.</p>';
        } else {
            list.innerHTML = templates.map(t => `
                <div class="template-card" data-filename="${t.filename}">
                    <div class="template-name">${t.name}</div>
                </div>
            `).join('');

            list.querySelectorAll('.template-card').forEach(card => {
                card.addEventListener('click', () => applyTemplate(card.dataset.filename));
            });
        }

        document.getElementById('template-modal').style.display = 'flex';
    } catch (err) {
        console.error('Template load error:', err);
    }
}

async function applyTemplate(filename) {
    try {
        const resp = await fetch(`/api/templates/${filename}`);
        const tmpl = await resp.json();

        // Set group_by
        if (tmpl.group_by) {
            document.getElementById('group-by-select').value = tmpl.group_by;
        }

        // Load metric rows
        if (tmpl.rows) {
            metricsGridApi.setGridOption('rowData', tmpl.rows);
        }

        // Load columns
        if (tmpl.columns) {
            columnsGridApi.setGridOption('rowData', tmpl.columns);
        }

        document.getElementById('template-modal').style.display = 'none';
    } catch (err) {
        alert('Error loading template: ' + err.message);
    }
}

// ---------------------------------------------------------------------------
// Loading helpers
// ---------------------------------------------------------------------------

document.getElementById('btn-view-reasoning').addEventListener('click', async () => {
    try {
        const resp = await fetch('/api/debug/llm-reasoning');
        const data = await resp.json();
        if (data.status) {
            alert(data.status);
            return;
        }
        const win = window.open('', '_blank', 'width=800,height=600');
        win.document.write(`<pre style="font-family:monospace;white-space:pre-wrap;padding:20px;font-size:13px;">`
            + `<h2>LLM Reasoning Trace</h2>`
            + `<p><b>Tokens:</b> prompt=${data.prompt_tokens}, completion=${data.completion_tokens}</p>`
            + `<p><b>Finish reason:</b> ${data.finish_reason}</p>`
            + `<hr><h3>Thinking (reasoning_content):</h3><pre>${escapeHtml(data.reasoning || '(empty)')}</pre>`
            + `<hr><h3>Content (actual output):</h3><pre>${escapeHtml(data.content || '(empty)')}</pre>`
            + `</pre>`);
    } catch (err) {
        alert('Error: ' + err.message);
    }
});

// ---------------------------------------------------------------------------
// AI Plan (LLM Step 1)
// ---------------------------------------------------------------------------

document.getElementById('btn-ai-plan').addEventListener('click', aiPlan);

async function aiPlan() {
    if (!uploadedFilename) {
        alert('Please upload a CSV first.');
        return;
    }

    const metrics = document.getElementById('ai-plan-input').value.trim();
    if (!metrics) {
        alert('Please describe the metrics you want in the scorecard.');
        return;
    }

    const columns = [];
    columnsGridApi.forEachNode(node => columns.push(node.data));

    if (!columns.length) {
        alert('Please add at least one scorecard column (dimension value) first.');
        return;
    }

    const statusEl = document.getElementById('ai-plan-status');
    statusEl.textContent = 'AI is planning... (this may take 30-90 seconds)';
    statusEl.className = 'running';

    const signal = startOperation();
    showLoading('LLM is analyzing your metrics and mapping them to CSV columns...');

    try {
        const resp = await fetch('/api/llm/plan', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                csv_filename: uploadedFilename,
                metrics: metrics,
                columns: columns,
                group_by: document.getElementById('group-by-select').value,
                rules: document.getElementById('rules-input').value.trim(),
            }),
            signal,
        });

        if (!resp.ok) {
            const err = await parseErrorResponse(resp);
            throw new Error(err.detail || 'Plan generation failed');
        }

        const data = await resp.json();
        const plan = data.plan;

        if (plan && plan.rows && plan.rows.length > 0) {
            metricsGridApi.setGridOption('rowData', plan.rows);
            statusEl.textContent = `Done! ${plan.rows.length} metrics mapped (${data.reasoning_tokens} tokens)`;
            statusEl.className = 'done';
        } else {
            statusEl.textContent = 'LLM returned an empty plan.';
            statusEl.className = 'error';
        }
    } catch (err) {
        if (isAbortError(err)) {
            statusEl.textContent = 'Cancelled.';
            statusEl.className = 'error';
        } else {
            statusEl.textContent = 'Error: ' + err.message;
            statusEl.className = 'error';
        }
    } finally {
        hideLoading();
    }
}

// ---------------------------------------------------------------------------
// Validate Results (LLM Step 3)
// ---------------------------------------------------------------------------

document.getElementById('btn-validate').addEventListener('click', validateResults);

async function validateResults() {
    if (!currentScorecardData) {
        alert('No results to validate. Calculate a scorecard first.');
        return;
    }

    const rows = [];
    metricsGridApi.forEachNode(node => rows.push(node.data));
    const columns = [];
    columnsGridApi.forEachNode(node => columns.push(node.data));

    const signal = startOperation();
    showLoading('LLM is reviewing your scorecard for anomalies...');

    try {
        const resp = await fetch('/api/llm/validate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                scorecard_def: { rows, columns },
                results: currentScorecardData,
                rules: document.getElementById('rules-input').value.trim(),
            }),
            signal,
        });

        if (!resp.ok) {
            const err = await parseErrorResponse(resp);
            throw new Error(err.detail || 'Validation failed');
        }

        const data = await resp.json();
        renderValidationReport(data.validation);
    } catch (err) {
        if (isAbortError(err)) {
            // Cancelled — silently ignore
        } else {
            alert('Validation error: ' + err.message);
        }
    } finally {
        hideLoading();
    }
}

function renderValidationReport(validation) {
    const container = document.getElementById('validation-report');
    const content = document.getElementById('validation-content');

    let html = '';
    if (validation.status === 'ok') {
        html = `<p class="validation-ok">All checks passed.</p>`;
    } else {
        html = `<p style="color:#d97706;font-weight:600;">Found ${validation.findings?.length || 0} issue(s):</p>`;
        if (validation.findings && validation.findings.length > 0) {
            html += '<ul class="validation-warnings">';
            validation.findings.forEach(f => {
                const sevClass = `validation-severity-${f.severity}`;
                html += `<li><span class="${sevClass}">[${f.severity.toUpperCase()}]</span> <b>${f.metric}</b>: ${f.issue}</li>`;
            });
            html += '</ul>';
        }
    }
    if (validation.summary) {
        html += `<p style="margin-top:8px;color:#4a5568;font-style:italic;">${validation.summary}</p>`;
    }

    content.innerHTML = html;
    container.style.display = 'block';
}

function escapeHtml(str) {
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function showLoading(text) {
    document.getElementById('loading-text').textContent = text || 'Loading...';
    document.getElementById('loading-overlay').style.display = 'flex';
    document.getElementById('btn-cancel-operation').style.display = 'inline-block';
}

function hideLoading() {
    document.getElementById('loading-overlay').style.display = 'none';
    document.getElementById('btn-cancel-operation').style.display = 'none';
}

function startOperation() {
    currentAbortController = new AbortController();
    return currentAbortController.signal;
}

function cancelOperation() {
    if (currentAbortController) {
        currentAbortController.abort();
        currentAbortController = null;
    }
}

function isAbortError(err) {
    return err.name === 'AbortError' || err.message?.includes('abort');
}

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

document.addEventListener('DOMContentLoaded', () => {
    initMetricsGrid();
    initColumnsGrid();

    document.getElementById('btn-cancel-operation').addEventListener('click', () => {
        cancelOperation();
    });
});
