/**
 * job-panel.js — 校招信息面板管理
 */

let currentJobInfo = null;

// ============ 校招面板 ============

async function refreshJobPanel() {
    const jobList = document.getElementById('jobList');

    try {
        const jobs = await api.getJobPanel();

        if (!jobs || jobs.length === 0) {
            jobList.innerHTML = '<div class="empty-hint">暂无校招信息<br>输入求职相关内容自动搜索</div>';
            return;
        }

        jobList.innerHTML = jobs.map(job => {
            // 判断截止日期是否临近（7天内）
            let deadlineClass = 'job-deadline';
            let deadlineText = '';
            if (job.deadline) {
                const deadline = new Date(job.deadline);
                const now = new Date();
                const daysLeft = Math.ceil((deadline - now) / (1000 * 60 * 60 * 24));
                if (daysLeft <= 7) {
                    deadlineClass += ' soon';
                }
                deadlineText = daysLeft <= 0
                    ? '⏰ 已截止'
                    : `⏰ ${isoToDisplay(job.deadline)} (${daysLeft}天后)`;
            }

            return `
                <div class="job-item" onclick="showJobDetail(${job.id})">
                    <div class="job-company">🏢 ${escapeHtml(job.company)}</div>
                    <div class="job-title">${escapeHtml(job.title || '校招信息')}</div>
                    ${deadlineText ? `<div class="${deadlineClass}">${deadlineText}</div>` : ''}
                    ${job.is_applied ? '<div style="color:#27ae60;font-size:11px;margin-top:2px;">✅ 已投递</div>' : ''}
                </div>
            `;
        }).join('');

    } catch (err) {
        console.error('获取校招信息失败:', err);
        jobList.innerHTML = '<div class="empty-hint">加载失败，请重试</div>';
    }
}

// ============ 校招详情弹窗 ============

async function showJobDetail(jobId) {
    const modal = document.getElementById('jobModal');
    const body = document.getElementById('jobModalBody');

    try {
        // 从列表中找到对应数据（简化：直接通过ID查找）
        const jobs = await api.getJobPanel();
        const job = jobs.find(j => j.id === jobId);

        if (!job) {
            alert('未找到该信息');
            return;
        }

        currentJobInfo = job;

        document.getElementById('jobModalTitle').textContent = job.company + ' - 校招信息';

        body.innerHTML = `
            <div class="form-group">
                <label>企业</label>
                <p style="font-size:15px;font-weight:600;">${escapeHtml(job.company)}</p>
            </div>
            <div class="form-group">
                <label>招聘标题</label>
                <p>${escapeHtml(job.title || '未提供')}</p>
            </div>
            <div class="form-group">
                <label>描述</label>
                <p style="white-space:pre-wrap;">${escapeHtml(job.description || '暂无详细描述')}</p>
            </div>
            <div class="form-group">
                <label>截止日期</label>
                <p style="color:${job.deadline ? 'var(--color-danger)' : 'inherit'};font-weight:600;">
                    ${job.deadline ? isoToDisplay(job.deadline) : '未提供'}
                </p>
            </div>
            ${job.url ? `
            <div class="form-group">
                <label>原文链接</label>
                <p><a href="${escapeHtml(job.url)}" target="_blank" style="color:var(--color-primary);">${escapeHtml(job.url)}</a></p>
            </div>` : ''}
            <div class="form-group">
                <label>信息来源</label>
                <p style="font-size:12px;color:var(--color-text-secondary);">${escapeHtml(job.source || '网络搜索')}</p>
            </div>
        `;

        // 更新「已投递」按钮状态
        const btnApplied = document.getElementById('btnJobApplied');
        btnApplied.textContent = job.is_applied ? '🔄 取消标记' : '✅ 标记已投递';
        btnApplied.onclick = () => toggleJobApplied(job);

        modal.style.display = 'flex';

    } catch (err) {
        console.error('获取详情失败:', err);
    }
}

function closeJobModal() {
    document.getElementById('jobModal').style.display = 'none';
    currentJobInfo = null;
}

async function toggleJobApplied(job) {
    try {
        const newStatus = !job.is_applied;
        await api.markJobApplied(job.id, newStatus);
        closeJobModal();
        await refreshJobPanel();
    } catch (err) {
        console.error('标记失败:', err);
        alert('操作失败，请重试');
    }
}

// ============ 搜索校招 ============

async function searchJobsManually(keywords) {
    const jobList = document.getElementById('jobList');
    const statusEl = document.getElementById('parseStatus');
    jobList.innerHTML = '<div class="empty-hint">🔍 正在搜索校招信息...</div>';

    try {
        const results = await api.searchJobs(keywords);

        if (results && results.length > 0) {
            await refreshJobPanel();
            await refreshCalendar();
            if (statusEl) {
                statusEl.textContent = '✅ 找到 ' + results.length + ' 条校招信息';
                statusEl.className = 'parse-status success';
            }
        } else {
            jobList.innerHTML = '<div class="empty-hint">未找到相关校招信息<br>请尝试其他关键词</div>';
        }
    } catch (err) {
        console.error('搜索失败:', err);
        jobList.innerHTML = '<div class="empty-hint">搜索失败，请重试</div>';
    }
}

/**
 * 从搜索框读取企业名并搜索
 */
async function searchSpecificCompany() {
    const input = document.getElementById('jobSearchInput');
    const company = input.value.trim();
    if (!company) {
        // 如果没输入，刷新全部
        await searchJobsManually(['校招']);
        return;
    }

    // 将企业名作为搜索关键词
    await searchJobsManually([company, '校招']);
    input.value = '';  // 清空搜索框
}

// ============ 工具 ============

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
