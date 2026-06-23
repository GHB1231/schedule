/**
 * app.js — 应用主逻辑，全局状态和弹窗管理
 */

// ============ 全局状态 ============
const AppState = {
    currentEvent: null,       // 当前编辑的事件
    lastParsedData: null,     // 最近一次智能解析结果
    isWaiting: false,         // 是否等待后端响应
};

// ============ 弹窗管理 ============

function openModal(eventData = null) {
    const modal = document.getElementById('eventModal');

    if (eventData) {
        // 编辑模式
        document.getElementById('modalTitle').textContent = '编辑事件';
        document.getElementById('evId').value = eventData.id || '';
        document.getElementById('evTitle').value = eventData.title || '';
        document.getElementById('evType').value = eventData.event_type || 'other';
        document.getElementById('evStart').value = formatDateTimeLocal(eventData.start_time);
        document.getElementById('evEnd').value = formatDateTimeLocal(eventData.end_time);
        document.getElementById('evLocation').value = eventData.location || '';
        document.getElementById('evDescription').value = eventData.description || '';
        document.getElementById('evPriority').value = eventData.priority || 0;
        document.getElementById('evSampleId').value = eventData._sample_id || '';

        document.getElementById('btnDelete').style.display = 'inline-block';
        AppState.currentEvent = eventData;
    } else {
        // 新增模式（解析结果回填）
        document.getElementById('modalTitle').textContent = '添加事件';
        document.getElementById('evId').value = '';
        document.getElementById('evSampleId').value = '';

        if (AppState.lastParsedData) {
            const d = AppState.lastParsedData;
            document.getElementById('evTitle').value = d.title || '';
            document.getElementById('evType').value = d.event_type || 'other';
            document.getElementById('evStart').value = formatDateTimeLocal(d.start_time);
            document.getElementById('evEnd').value = formatDateTimeLocal(d.end_time);
            document.getElementById('evLocation').value = d.location || '';
            document.getElementById('evDescription').value = d.description || '';
            document.getElementById('evPriority').value = d.priority || 0;
        }

        document.getElementById('btnDelete').style.display = 'none';
        AppState.currentEvent = null;
    }

    modal.style.display = 'flex';
}

function closeModal() {
    document.getElementById('eventModal').style.display = 'none';
    AppState.currentEvent = null;
    AppState.lastParsedData = null;
}

function showManualForm() {
    AppState.lastParsedData = null;
    openModal(null);
}

// ============ 保存 & 删除事件 ============

async function handleSaveEvent() {
    const eventData = {
        title: document.getElementById('evTitle').value.trim(),
        event_type: document.getElementById('evType').value,
        start_time: document.getElementById('evStart').value,
        end_time: document.getElementById('evEnd').value || null,
        location: document.getElementById('evLocation').value.trim(),
        description: document.getElementById('evDescription').value.trim(),
        priority: parseInt(document.getElementById('evPriority').value),
        source: 'manual',
    };

    if (!eventData.title || !eventData.start_time) {
        alert('请填写标题和开始时间');
        return;
    }

    const eventId = document.getElementById('evId').value;
    const sampleId = document.getElementById('evSampleId').value;

    try {
        if (eventId) {
            // 更新已有事件
            await api.updateEvent(parseInt(eventId), eventData);

            // 如果有 sample_id，记录修正
            if (sampleId) {
                await api.correctParse(parseInt(sampleId), eventData);
            }
        } else if (sampleId) {
            // 来自智能解析：只调用 confirmParse 保存一次（含学习记录）
            await api.confirmParse({
                ...eventData,
                tags: JSON.stringify(AppState.lastParsedData?.tags || []),
                _sample_id: parseInt(sampleId),
            });
        } else {
            // 手动添加：只调用 addEvent 保存一次
            await api.addEvent(eventData);
        }

        closeModal();
        await refreshCalendar();
        await refreshLearningStats();

    } catch (err) {
        console.error('保存失败:', err);
        alert('保存失败: ' + err);
    }
}

async function handleDeleteEvent() {
    const eventId = document.getElementById('evId').value;
    if (!eventId) return;

    if (!confirm('确定要删除这个事件吗？')) return;

    try {
        await api.deleteEvent(parseInt(eventId));
        closeModal();
        await refreshCalendar();
    } catch (err) {
        console.error('删除失败:', err);
        alert('删除失败: ' + err);
    }
}

// ============ 工具函数 ============

function formatDateTimeLocal(isoStr) {
    if (!isoStr) return '';
    // ISO 8601 → datetime-local input 格式
    try {
        const dt = new Date(isoStr);
        if (isNaN(dt.getTime())) return isoStr.substring(0, 16);
        const pad = (n) => String(n).padStart(2, '0');
        return `${dt.getFullYear()}-${pad(dt.getMonth()+1)}-${pad(dt.getDate())}T${pad(dt.getHours())}:${pad(dt.getMinutes())}`;
    } catch {
        return isoStr.substring(0, 16);
    }
}

function isoToDisplay(isoStr) {
    if (!isoStr) return '';
    try {
        const dt = new Date(isoStr);
        if (isNaN(dt.getTime())) return isoStr;
        const pad = (n) => String(n).padStart(2, '0');
        return `${dt.getMonth()+1}月${dt.getDate()}日 ${pad(dt.getHours())}:${pad(dt.getMinutes())}`;
    } catch {
        return isoStr;
    }
}

// ============ 点击弹窗外部关闭 ============
document.addEventListener('click', (e) => {
    if (e.target.classList.contains('modal-overlay')) {
        closeModal();
        closeJobModal();
    }
});

// ============ 快捷键 ============
document.addEventListener('keydown', (e) => {
    // Escape 关闭弹窗
    if (e.key === 'Escape') {
        closeModal();
        closeJobModal();
    }
    // Ctrl+Enter 从输入框提交
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        const input = document.getElementById('quickInput');
        if (document.activeElement === input) {
            handleAddEvent();
        }
    }
});

// ============ 初始化 ============
async function initApp() {
    try {
        await refreshCalendar();
        await refreshJobPanel();
        await refreshLearningStats();
        console.log('[OK] 应用初始化完成');
    } catch (err) {
        console.error('初始化失败:', err);
    }
}

// ============ 侧边栏折叠 ============

function toggleSidePanel() {
    const panel = document.getElementById('sidePanel');
    panel.classList.toggle('collapsed');
    // 折叠后刷新日历大小
    if (calendar) {
        setTimeout(() => calendar.updateSize(), 300);
    }
}

// 手机屏幕默认折叠
function autoCollapseOnMobile() {
    if (window.innerWidth <= 768) {
        document.getElementById('sidePanel').classList.add('collapsed');
    }
}

// ============ 退出登录 ============

async function doLogout() {
    await fetch('/logout', { method: 'POST' });
    window.location.href = '/login.html';
}

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', () => {
    autoCollapseOnMobile();
    initApp();
});
