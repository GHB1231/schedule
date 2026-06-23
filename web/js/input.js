/**
 * input.js — 智能输入处理
 */

// ============ 智能添加事件 ============

async function handleAddEvent() {
    const inputEl = document.getElementById('quickInput');
    const statusEl = document.getElementById('parseStatus');
    const text = inputEl.value.trim();

    if (!text) {
        inputEl.focus();
        statusEl.textContent = '请输入日程内容';
        statusEl.className = 'parse-status error';
        return;
    }

    if (AppState.isWaiting) return;

    // UI 加载状态
    AppState.isWaiting = true;
    document.getElementById('btnAdd').disabled = true;
    statusEl.textContent = '🔍 AI 正在解析...';
    statusEl.className = 'parse-status loading';

    try {
        // 调用后端智能解析
        const parsed = await api.parseInput(text);

        if (parsed._parse_error) {
            throw new Error(parsed._parse_error);
        }

        // 存储解析结果
        AppState.lastParsedData = parsed;
        AppState.currentEvent = null;

        // 打开弹窗让用户确认
        openModal(null);

        // 预填解析结果后更新显示
        document.getElementById('modalTitle').textContent = '确认 AI 解析结果';
        document.getElementById('evTitle').value = parsed.title || text;
        document.getElementById('evType').value = parsed.event_type || 'other';
        document.getElementById('evStart').value = formatDateTimeLocal(parsed.start_time);
        document.getElementById('evEnd').value = formatDateTimeLocal(parsed.end_time);
        document.getElementById('evLocation').value = parsed.location || '';
        document.getElementById('evDescription').value = parsed.description || '';
        document.getElementById('evPriority').value = parsed.priority || 0;
        document.getElementById('evSampleId').value = parsed._sample_id || '';
        document.getElementById('btnDelete').style.display = 'none';

        statusEl.textContent = '✅ 解析完成，请确认后保存';
        statusEl.className = 'parse-status success';
        inputEl.value = '';  // 清空输入框

        // 如果解析结果是求职相关，自动触发校招搜索
        if (parsed._trigger_job_search) {
            const keywords = parsed._job_keywords || ['校招'];
            statusEl.textContent = '🔍 正在搜索校招信息...';
            searchJobsManually(keywords);
        }

    } catch (err) {
        console.error('解析失败:', err);
        statusEl.textContent = '❌ 解析失败: ' + err.message;
        statusEl.className = 'parse-status error';

        // 解析失败时，仍然打开编辑弹窗让用户手动填写
        AppState.lastParsedData = null;
        openModal(null);
        document.getElementById('evTitle').value = text;
    } finally {
        AppState.isWaiting = false;
        document.getElementById('btnAdd').disabled = false;
    }
}

// ============ 手动添加（复用弹窗） ============

function showManualForm() {
    AppState.lastParsedData = null;
    openModal(null);
}

// ============ 学习统计更新 ============

async function refreshLearningStats() {
    try {
        const stats = await api.getLearningStats();

        document.getElementById('lTotal').textContent = stats.total_samples;
        document.getElementById('lCorrected').textContent = stats.corrected_samples;
        document.getElementById('lAccuracy').textContent = stats.accuracy + '%';

        // 更新顶部栏统计
        document.getElementById('statAccuracy').textContent =
            '解析准确率: ' + stats.accuracy + '%';
        document.getElementById('statSamples').textContent =
            '样本数: ' + stats.total_samples;

    } catch (err) {
        console.error('获取学习统计失败:', err);
    }
}
