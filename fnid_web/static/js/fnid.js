/* =================================================================
   FNID Area 3 Operational Portal - Frontend JavaScript
   ================================================================= */

document.addEventListener('DOMContentLoaded', function() {

    // Initialize DataTables on all tables with .fnid-table class
    document.querySelectorAll('.fnid-table').forEach(function(table) {
        if ($.fn.DataTable.isDataTable(table)) return;
        $(table).DataTable({
            pageLength: 25,
            order: [[0, 'desc']],
            responsive: true,
            dom: '<"row"<"col-sm-6"l><"col-sm-6"f>>rtip',
            language: {
                search: "Search records:",
                lengthMenu: "Show _MENU_ records",
                info: "Showing _START_ to _END_ of _TOTAL_ records",
                emptyTable: "No records found. Click 'New Entry' to add.",
            }
        });
    });

    // Auto-calculate 48-hour deadline from arrest date/time
    var arrestDate = document.getElementById('arrest_date');
    var arrestTime = document.getElementById('arrest_time');
    var deadline = document.getElementById('deadline_48hr');
    if (arrestDate && arrestTime && deadline) {
        function calc48hr() {
            if (arrestDate.value && arrestTime.value) {
                var dt = new Date(arrestDate.value + 'T' + arrestTime.value);
                dt.setHours(dt.getHours() + 48);
                deadline.value = dt.toISOString().slice(0, 16).replace('T', ' ');
            }
        }
        arrestDate.addEventListener('change', calc48hr);
        arrestTime.addEventListener('change', calc48hr);
    }

    // Form validation enhancement
    document.querySelectorAll('form.needs-validation').forEach(function(form) {
        form.addEventListener('submit', function(event) {
            if (!form.checkValidity()) {
                event.preventDefault();
                event.stopPropagation();
            }
            form.classList.add('was-validated');
        });
    });

    // Confirmation for submit action
    document.querySelectorAll('.btn-submit-record').forEach(function(btn) {
        btn.addEventListener('click', function(e) {
            if (!confirm('Submit this record? Once submitted, changes will be tracked in the audit log.')) {
                e.preventDefault();
            }
        });
    });

    // Status badge coloring
    document.querySelectorAll('[data-status]').forEach(function(el) {
        var status = el.getAttribute('data-status').toLowerCase();
        if (status.includes('draft'))      el.classList.add('badge-draft');
        else if (status.includes('submitted')) el.classList.add('badge-submitted');
        else if (status.includes('edited'))    el.classList.add('badge-edited');
        else if (status.includes('approved'))  el.classList.add('badge-approved');
        else if (status.includes('rejected'))  el.classList.add('badge-rejected');
    });

    // SOP checklist progress calculation
    var sopForm = document.getElementById('sop-checklist-form');
    if (sopForm) {
        function updateProgress() {
            var checks = sopForm.querySelectorAll('select.sop-check');
            var total = checks.length;
            var done = 0;
            checks.forEach(function(sel) {
                if (sel.value === 'Yes') done++;
            });
            var pct = total > 0 ? Math.round((done / total) * 100) : 0;
            var bar = document.getElementById('sop-progress-bar');
            var label = document.getElementById('sop-progress-label');
            if (bar) {
                bar.style.width = pct + '%';
                bar.setAttribute('aria-valuenow', pct);
                bar.className = 'progress-bar';
                if (pct >= 90) bar.classList.add('bg-success');
                else if (pct >= 60) bar.classList.add('bg-warning');
                else bar.classList.add('bg-danger');
            }
            if (label) label.textContent = pct + '% Complete (' + done + '/' + total + ')';
        }
        sopForm.querySelectorAll('select.sop-check').forEach(function(sel) {
            sel.addEventListener('change', updateProgress);
        });
        updateProgress();
    }

    // Chart rendering helper
    window.fnidChart = function(canvasId, type, labels, datasets, options) {
        var ctx = document.getElementById(canvasId);
        if (!ctx) return null;
        var defaults = {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: type === 'pie' || type === 'doughnut' ? 'right' : 'top',
                    labels: { font: { size: 11 } }
                }
            }
        };
        return new Chart(ctx, {
            type: type,
            data: { labels: labels, datasets: datasets },
            options: Object.assign(defaults, options || {})
        });
    };

});
