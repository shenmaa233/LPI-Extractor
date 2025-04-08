/**
 * 激光物理论文参数提取系统 - 主要脚本
 */

document.addEventListener("DOMContentLoaded", function() {
    // 初始化进度条
    initProgressBars();
    
    // 初始化工具提示
    initTooltips();
    
    // 初始化参数显示
    initParameterDisplay();
    
    // 初始化参数表格排序
    initTableSort();
});

/**
 * 初始化进度条
 */
function initProgressBars() {
    document.querySelectorAll('.progress-bar').forEach(function(progressBar) {
        let width = progressBar.getAttribute('data-width');
        if (width) {
            progressBar.style.width = width + '%';
        }
    });
}

/**
 * 初始化工具提示
 */
function initTooltips() {
    // 检查Bootstrap是否已加载
    if (typeof bootstrap !== 'undefined') {
        const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
        tooltipTriggerList.map(function(tooltipTriggerEl) {
            return new bootstrap.Tooltip(tooltipTriggerEl);
        });
    }
}

/**
 * 初始化参数表格排序
 */
function initTableSort() {
    const tables = document.querySelectorAll('table.sortable');
    
    tables.forEach(table => {
        const headers = table.querySelectorAll('th');
        
        headers.forEach((header, index) => {
            if (!header.classList.contains('no-sort')) {
                header.addEventListener('click', () => {
                    sortTable(table, index);
                });
                header.style.cursor = 'pointer';
                header.title = '点击排序';
            }
        });
    });
}

/**
 * 排序表格
 */
function sortTable(table, columnIndex) {
    const tbody = table.querySelector('tbody');
    const rows = Array.from(tbody.querySelectorAll('tr'));
    const header = table.querySelectorAll('th')[columnIndex];
    const isNumeric = header.classList.contains('numeric');
    const isAsc = header.classList.contains('asc');
    
    // 更新排序方向
    const allHeaders = table.querySelectorAll('th');
    allHeaders.forEach(h => {
        h.classList.remove('asc', 'desc');
    });
    
    header.classList.add(isAsc ? 'desc' : 'asc');
    
    // 排序行
    rows.sort((a, b) => {
        const cellA = a.querySelectorAll('td')[columnIndex].textContent.trim();
        const cellB = b.querySelectorAll('td')[columnIndex].textContent.trim();
        
        if (isNumeric) {
            const numA = parseFloat(cellA) || 0;
            const numB = parseFloat(cellB) || 0;
            return isAsc ? numB - numA : numA - numB;
        } else {
            return isAsc ? 
                cellB.localeCompare(cellA, 'zh-CN') : 
                cellA.localeCompare(cellB, 'zh-CN');
        }
    });
    
    // 重新添加行
    rows.forEach(row => {
        tbody.appendChild(row);
    });
}

/**
 * 初始化参数显示
 */
function initParameterDisplay() {
    // 处理参数展开/折叠
    document.querySelectorAll('.parameter-category-toggle').forEach(toggle => {
        toggle.addEventListener('click', function() {
            const targetId = this.getAttribute('data-target');
            const target = document.getElementById(targetId);
            
            if (target) {
                target.classList.toggle('show');
                this.querySelector('.bi').classList.toggle('bi-chevron-down');
                this.querySelector('.bi').classList.toggle('bi-chevron-up');
            }
        });
    });
    
    // 处理详细信息展开
    document.querySelectorAll('.parameter-info-toggle').forEach(toggle => {
        toggle.addEventListener('click', function() {
            const targetId = this.getAttribute('data-target');
            const target = document.getElementById(targetId);
            
            if (target) {
                target.classList.toggle('d-none');
                this.querySelector('.bi').classList.toggle('bi-plus-circle');
                this.querySelector('.bi').classList.toggle('bi-dash-circle');
            }
        });
    });
}

/**
 * 导出参数至CSV
 */
function exportParametersToCSV(parameters, filename) {
    if (!parameters || parameters.length === 0) {
        alert('没有可导出的参数');
        return;
    }
    
    let csvContent = "data:text/csv;charset=utf-8,";
    
    // CSV头
    csvContent += "参数名称,数值,单位,类别,论文标题,论文ID,可信度\n";
    
    // 添加参数行
    parameters.forEach(param => {
        let row = [
            param.parameter_name || "",
            param.value || "",
            param.unit || "",
            param.category || "",
            param.paper_title || "",
            param.paper_id || "",
            param.confidence_score || ""
        ].map(cell => `"${cell.replace(/"/g, '""')}"`).join(",");
        
        csvContent += row + "\n";
    });
    
    // 创建下载链接
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", filename || "laser_parameters.csv");
    document.body.appendChild(link);
    
    // 模拟点击下载
    link.click();
    
    // 清理
    document.body.removeChild(link);
}

/**
 * 参数搜索表单验证
 */
function validateSearchForm() {
    const form = document.getElementById('parameterSearchForm');
    if (!form) return true;
    
    const query = form.querySelector('input[name="q"]').value.trim();
    return query.length > 0;
} 