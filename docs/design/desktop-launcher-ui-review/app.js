const $ = selector => document.querySelector(selector)
const $$ = selector => [...document.querySelectorAll(selector)]
const icon = id => `<svg aria-hidden="true"><use href="#${id}"/></svg>`
const params = new URLSearchParams(location.search)
let currentPage = ['home', 'versions', 'engines', 'logs', 'settings'].includes(params.get('view')) ? params.get('view') : 'home'
let currentState = ['stopped', 'starting', 'running', 'stopping', 'error'].includes(params.get('state')) ? params.get('state') : 'stopped'
let currentSetting = params.get('setting') || 'appearance'
let transitionTimer
let sourceFilter = 'all'
let follow = true
let toastTimer
let logSequence = 0
const appearancePreview = { blur: true, opaque: false, mask: 62 }
const logEntries = [
  ['19:55:10.042', 'INFO', 'launcher', '启动器就绪，已恢复上次选择的安装位置。'],
  ['19:55:10.049', 'INFO', 'launcher', '当前版本：Next Trainer 3.3.1-dev。'],
  ['19:55:10.061', 'INFO', 'environment', '主程序环境检查完成，文件验证通过。'],
  ['19:55:10.082', 'INFO', 'environment', 'Kohya 独立环境可用。'],
  ['19:55:11.203', 'INFO', 'launcher', '收到启动训练器请求。'],
  ['19:55:11.226', 'INFO', 'service', '创建本次受管服务进程。'],
  ['19:55:11.557', 'INFO', 'service', 'Next Trainer 3.3.1-dev，准备本机服务。'],
  ['19:55:12.010', 'INFO', 'service', 'Application startup complete.'],
  ['19:55:12.041', 'INFO', 'service', '服务正在监听 http://127.0.0.1:7584。'],
  ['19:55:12.085', 'INFO', 'launcher', '服务健康检查通过，网页入口已就绪。'],
  ['19:55:12.086', 'INFO', 'launcher', '运行状态已更新：运行中。'],
  ['19:55:12.094', 'INFO', 'environment', '训练引擎的详细日志会在任务开始后单独记录。']
].map(([time, level, source, message]) => ({ time, level, source, message, id: ++logSequence }))
const sourceNames = { launcher: '启动器', service: '服务', environment: '环境' }
function escapeHtml(text) { return String(text).replace(/[&<>"']/g, value => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[value]) }
function toast(message) { clearTimeout(toastTimer); $('#toast').textContent = message; $('#toast').hidden = false; toastTimer = setTimeout(() => $('#toast').hidden = true, 3000) }
function dialog(title, text) { $('#dialogTitle').textContent = title; $('#dialogText').textContent = text; $('#mockDialog').showModal() }
function updateUrl() { const query = new URLSearchParams({ view: currentPage, state: currentState }); if (currentPage === 'settings') query.set('setting', currentSetting); history.replaceState(null, '', `${location.pathname}?${query}`) }
function navigate(page) {
  currentPage = page
  $('#app').dataset.page = page
  $$('.page').forEach(element => element.classList.toggle('active', element.id === `page-${page}`))
  $$('.rail-link').forEach(element => { element.classList.toggle('active', element.dataset.page === page); element.setAttribute('aria-current', element.dataset.page === page ? 'page' : 'false') })
  if (page === 'logs') { $('.log-dot').hidden = true; renderLogs() }
  updateUrl()
}
function addLog(source, message, level = 'INFO') { const time = new Date().toLocaleTimeString('zh-CN', { hour12: false }) + '.000'; logEntries.push({ id: ++logSequence, time, level, source, message }); if (level === 'ERROR' && currentPage !== 'logs') $('.log-dot').hidden = false; renderLogs() }
function renderState() {
  const config = {
    stopped: { title: '准备就绪', status: '环境已准备就绪', caption: '所有准备就绪', label: '启动训练器', icon: 'play', secondary: '安装位置', secondaryIcon: 'folder', foot: '3.3.1-dev <span>·</span> Kohya 已就绪' },
    starting: { title: '正在启动', status: '正在启动训练器…', caption: '正在等待服务就绪', label: '正在启动…', icon: 'refresh', secondary: '取消启动', secondaryIcon: 'stop', foot: '服务就绪后，将立即显示网页入口' },
    running: { title: '服务已就绪', status: '训练器服务运行中', caption: 'http://127.0.0.1:7584', label: '打开训练网页', icon: 'external', secondary: '停止服务', secondaryIcon: 'stop', foot: '本机服务 <span>·</span> 运行中' },
    stopping: { title: '正在停止', status: '正在停止训练器…', caption: '正在结束本次服务', label: '正在停止…', icon: 'refresh', secondary: '查看日志', secondaryIcon: 'logs', foot: '服务退出后，即可重新启动' },
    error: { title: '启动失败', status: '服务未能启动', caption: '检查日志后可再次尝试', label: '重试启动', icon: 'refresh', secondary: '查看日志', secondaryIcon: 'logs', foot: '本机安装仍保留，不自动重新安装' }
  }[currentState]
  $('#titleState').innerHTML = `<i style="background:${currentState === 'error' ? '#e1a3a6' : currentState === 'starting' || currentState === 'stopping' ? '#c8bf9d' : '#a4ceb9'}"></i>${config.title}`
  $('#homeStatus').textContent = config.status
  $('#serviceCaption').textContent = config.caption
  $('#copyAddress').hidden = currentState !== 'running'
  $('#launchButton').innerHTML = icon(config.icon) + `<span>${config.label}</span>`
  $('#launchButton').disabled = ['starting', 'stopping'].includes(currentState)
  if ($('#launchButton').disabled) $('#launchButton svg').classList.add('spin')
  $('#homeSecondary').innerHTML = icon(config.secondaryIcon) + `<span>${config.secondary}</span>`
  $('#launchFootnote').innerHTML = config.foot
  $('#homeError').hidden = currentState !== 'error'
  updateUrl()
}
function changeState(state) { currentState = state; renderState() }
function startService() {
  clearTimeout(transitionTimer)
  changeState('starting')
  addLog('launcher', '收到启动训练器请求，正在准备服务。')
  transitionTimer = setTimeout(() => {
    addLog('service', 'Application startup complete.')
    addLog('launcher', '服务健康检查通过，网页入口已就绪。')
    changeState('running')
  }, 1500)
}
function stopService() {
  clearTimeout(transitionTimer)
  changeState('stopping')
  addLog('launcher', '收到停止请求，正在结束本次受管服务。')
  transitionTimer = setTimeout(() => { addLog('launcher', '服务已退出，运行状态已更新。'); changeState('stopped') }, 1000)
}
function visibleLogs() { const search = $('#logSearch').value.toLowerCase(); const level = $('#logLevel').value; return logEntries.filter(entry => (sourceFilter === 'all' || entry.source === sourceFilter) && (level === 'all' || entry.level === level) && `${entry.time} ${entry.level} ${sourceNames[entry.source]} ${entry.message}`.toLowerCase().includes(search)) }
function renderLogs() {
  const entries = visibleLogs()
  $('#logRows').innerHTML = entries.map(entry => `<div class="log-line${entry.level === 'ERROR' ? ' highlight' : ''}" data-level="${entry.level}" id="log-${entry.id}"><span class="log-time">${entry.time}</span><span class="log-level">${entry.level}</span><span class="log-source">${sourceNames[entry.source]}</span><span class="log-message">${escapeHtml(entry.message)}</span></div>`).join('')
  $('#logCount').textContent = `${entries.length} / ${logEntries.length} 条记录`
  $('#logEmpty').hidden = entries.length !== 0
  if (follow) $('#terminal').scrollTop = $('#terminal').scrollHeight
}
function settingsContent(setting) {
  const templates = {
    appearance: `<h2>外观</h2><div class="setting-label">主题</div><div class="theme-options"><button class="theme-choice selected" data-theme="dark" title="深色主题"><span class="mini-app"></span></button><button class="theme-choice light-theme" disabled title="浅色主题待设计，不可选择"><span class="mini-app"></span></button></div><div class="theme-labels"><span>深色</span><span>浅色 · 待设计</span></div><h3>背景</h3><p class="setting-description">使用你喜欢的图片作为启动器背景。其他页面沿用同一图片的柔和模糊效果。</p><button class="soft-button" data-toast="设计稿：正式版本将打开本地图片选择器">${icon('image')}选择背景图片</button><div class="switch-line"><button class="toggle on" data-effect="blur" aria-label="背景模糊" aria-pressed="true"><i></i></button>内容页面使用模糊背景</div><h3>阅读与对比度</h3><div class="setting-label">内容遮罩</div><div class="range-line"><input type="range" min="30" max="85" value="62" aria-label="内容遮罩强度"><span>62%</span></div><div class="switch-line"><button class="toggle" data-effect="opaque" aria-label="减少透明效果" aria-pressed="false"><i></i></button>减少透明效果</div><div class="setting-apply"><button class="soft-button" data-toast="已在当前原型中预览外观变化；正式版本将保存设置">${icon('check')}应用</button><span>背景只影响启动器，不影响训练网页。</span></div>`,
    network: `<h2>网络</h2><div class="setting-label">连接方式</div><select aria-label="连接方式"><option>使用当前代理配置</option><option>直连</option><option>自定义代理</option></select><p class="setting-description">此设置供启动器下载与其管理的服务使用。</p><div class="setting-row"><div class="setting-label">HTTP / HTTPS 代理</div><input class="setting-input" aria-label="代理地址" value="http://127.0.0.1:11809"></div><button class="soft-button" data-toast="设计稿：连接检查未发送真实网络请求">${icon('network')}测试连接</button><h3>下载来源</h3><div class="setting-row flex-row"><div><div class="setting-label">PyPI</div><select aria-label="PyPI来源"><option>自动（引擎默认）</option><option>官方源</option></select></div><div><div class="setting-label">PyTorch</div><select aria-label="PyTorch来源"><option>自动（引擎默认）</option><option>官方源</option></select></div></div><div class="setting-row flex-row"><div><div class="setting-label">Hugging Face</div><select aria-label="HF来源"><option>自动（引擎默认）</option><option>官方源</option></select></div><div><div class="setting-label">GitHub</div><select aria-label="GitHub来源"><option>自动（引擎默认）</option><option>官方源</option></select></div></div><div class="setting-apply"><button class="soft-button" data-toast="设计稿：已演示网络设置保存">${icon('check')}保存</button><span>不修改系统代理。</span></div>`,
    profiles: `<h2>用户资料</h2><div class="setting-label">当前资料</div><div class="setting-description">训练配置与个人资料独立保存，切换版本时继续使用。</div><input class="setting-input" aria-label="资料目录" readonly value="F:\\NextTrainerLauncherSandbox\\u13\\profiles\\default"><div style="margin-top:13px"><button class="soft-button" data-toast="设计稿：定位当前资料目录">${icon('folder')}打开资料目录</button></div><h3>导入已有资料</h3><p class="setting-description">从已有安装中选择资料，先预览来源与冲突，再确认导入。导入后仍保留原资料。</p><button class="soft-button" data-toast="设计稿：选择来源后展示导入预览">${icon('folder')}选择导入来源</button><h3>资料快照</h3><p class="setting-description">版本切换或资料变更前创建的快照，会在对应操作详情中显示。</p><button class="soft-button" data-toast="设计稿：打开已有资料快照列表">查看快照</button>`,
    security: `<h2>安全与更新</h2><div class="setting-label">启动器版本</div><p class="setting-description">0.2 开发候选</p><button class="soft-button" data-toast="设计稿：检查可信启动器更新">${icon('refresh')}检查启动器更新</button><h3>训练器更新</h3><p class="setting-description">训练器版本独立管理；先验证发布清单，再展示可安装版本。</p><button class="soft-button" data-goto="versions">管理训练器版本${icon('chevron')}</button><h3>发布信任</h3><div class="switch-line"><span class="good">${icon('shield')}</span>固定发布清单与资产摘要验证</div><p class="setting-description">安装与修复前核对来源和文件身份。遇到验证失败时保留现场，并在日志中给出原因。</p><button class="soft-button" data-toast="设计稿：展开信任根、清单身份及验证结果">查看验证详情</button>`,
    about: `<div class="about-symbol"><img src="assets/home-logo.webp" alt="Next Trainer"></div><h2 class="about-title">Next Trainer</h2><div class="about-copyright">桌面启动器 · 安装、管理与环境恢复</div><div class="about-version">当前版本：<b>0.2 开发候选</b></div><button class="soft-button" data-toast="设计稿：检查可信启动器更新">${icon('refresh')}检查更新</button><h3>相关链接</h3><div class="setting-links"><button data-toast="项目主页：github.com/wochenlong/lora-scripts-next">项目主页</button><button data-toast="设计稿：反馈问题入口">反馈问题</button><button data-toast="设计稿：更新说明入口">更新日志</button><button data-toast="设计稿：第三方开源许可与致谢">开源许可与致谢</button></div><p class="setting-description" style="margin-top:29px">当前画面为交互审稿原型，背景仅用于视觉参考。</p>`
  }
  currentSetting = Object.hasOwn(templates, setting) ? setting : 'appearance'
  $('#settingsContent').innerHTML = templates[currentSetting]
  if (currentSetting === 'appearance') {
    for (const effect of ['blur', 'opaque']) {
      const control = $(`[data-effect="${effect}"]`)
      control.classList.toggle('on', appearancePreview[effect]); control.setAttribute('aria-pressed', String(appearancePreview[effect]))
    }
    const slider = $('#settingsContent input[type="range"]'); slider.value = appearancePreview.mask; slider.nextElementSibling.textContent = appearancePreview.mask + '%'
  }
  $$('[data-setting]').forEach(element => element.classList.toggle('selected', element.dataset.setting === currentSetting))
  updateUrl()
}
document.addEventListener('click', async event => {
  const button = event.target.closest('button')
  if (!button || button.disabled) return
  if (button.dataset.page) navigate(button.dataset.page)
  if (button.dataset.goto) navigate(button.dataset.goto)
  if (button.dataset.setting) settingsContent(button.dataset.setting)
  if (button.dataset.toast) toast(button.dataset.toast)
  if (button.classList.contains('window-close') || button.closest('.window-controls')) toast('这是设计稿，窗口控制在正式桌面版中生效')
  if (button.dataset.source) { sourceFilter = button.dataset.source; $$('[data-source]').forEach(item => item.classList.toggle('selected', item === button)); renderLogs() }
  if (button.dataset.releaseTab) {
    $$('[data-release-tab]').forEach(item => item.classList.toggle('selected', item === button))
    $('#releaseCopy').innerHTML = {
      current: '<div><span>主程序与网页资源已就绪</span><span class="quiet">本机</span></div><div><span>Kohya 训练环境可用</span><span class="quiet">已验证</span></div><button class="text-row" data-goto="versions">管理版本与安装位置' + icon('chevron') + '</button>',
      updates: '<div><span>改进启停状态与网页入口响应</span><span class="quiet">设计中</span></div><div><span>独立日志页，集中查看运行记录</span></div><button class="text-row" data-goto="versions">查看版本与更新说明' + icon('chevron') + '</button>',
      help: '<div><span>1. 启动训练器并打开训练网页</span></div><div><span>2. 在网页中配置并提交训练</span></div><button class="text-row" data-goto="logs">遇到问题？查看运行日志' + icon('chevron') + '</button>'
    }[button.dataset.releaseTab]
  }
  if (button.id === 'launchButton') {
    if (['stopped', 'error'].includes(currentState)) startService()
    else if (currentState === 'running') dialog('训练网页已就绪', '正式版本将打开本次受管服务的本机网页。当前为设计稿，不连接或控制实际训练服务。')
  }
  if (button.id === 'homeSecondary') {
    if (currentState === 'running') stopService()
    else if (currentState === 'starting') { clearTimeout(transitionTimer); changeState('stopped'); addLog('launcher', '用户已取消本次模拟启动。') }
    else if (currentState !== 'stopped') navigate('logs')
    else toast('安装位置：F:\\NextTrainerLauncherSandbox\\u13')
  }
  if (button.hasAttribute('data-error-log')) { sourceFilter = 'all'; $('#logLevel').value = 'ERROR'; navigate('logs') }
  if (button.id === 'followLogs') { follow = !follow; button.classList.toggle('paused', !follow); renderLogs() }
  if (button.id === 'copyLogs') {
    const text = visibleLogs().map(entry => `${entry.time} ${entry.level} [${sourceNames[entry.source]}] ${entry.message}`).join('\n')
    try { await navigator.clipboard.writeText(text); toast('已复制当前可见日志') } catch { dialog('复制日志', '此浏览器未授予剪贴板权限，可使用“导出”保存日志文本。') }
  }
  if (button.id === 'copyAddress') {
    try { await navigator.clipboard.writeText('http://127.0.0.1:7584'); toast('已复制设计稿示例地址') } catch { dialog('服务地址', 'http://127.0.0.1:7584（仅为设计稿示例地址）') }
  }
  if (button.id === 'guiRepair') dialog('主程序精准修复', '此入口承接已有主程序检查与修复：先核对实际安装，展示受影响组件和写入计划，再确认执行。当前设计稿仅演示入口，不运行检查或修复。')
  if (button.id === 'advancedRecovery') dialog('高级恢复', '基础 Python 恢复、主程序实例重建和登记恢复统一放在此处。正式执行前展示目标、变更范围与回退信息。当前为入口示意，不执行真实操作。')
  if (button.id === 'exportLogs') {
    const text = 'Next Trainer 设计稿 · 虚构示例日志\n' + visibleLogs().map(entry => `${entry.time} ${entry.level} [${sourceNames[entry.source]}] ${entry.message}`).join('\n')
    const href = URL.createObjectURL(new Blob([text], { type: 'text/plain;charset=utf-8' })); const anchor = document.createElement('a'); anchor.href = href; anchor.download = 'next-trainer-demo-logs.txt'; anchor.click(); setTimeout(() => URL.revokeObjectURL(href), 1000); toast('已导出设计稿示例日志')
  }
  if (button.classList.contains('toggle')) {
    button.classList.toggle('on'); button.setAttribute('aria-pressed', String(button.classList.contains('on')))
    if (button.dataset.effect === 'blur') { appearancePreview.blur = button.classList.contains('on'); $('#app').classList.toggle('no-background-blur', !appearancePreview.blur) }
    if (button.dataset.effect === 'opaque') { appearancePreview.opaque = button.classList.contains('on'); $('#app').classList.toggle('reduce-transparency', appearancePreview.opaque) }
  }
  if (button.dataset.theme) { $$('.theme-choice').forEach(item => item.classList.toggle('selected', item === button)); if (button.dataset.theme === 'light') toast('浅色主题为备选方向，本轮主稿采用深色') }
  if (button.id === 'checkVersions') toast('设计稿：当前展示本机已安装的开发候选')
  if (button.id === 'availableVersions') toast('设计稿：可安装列表由可信发布清单提供，不预置虚构稳定版')
  if (button.id === 'versionMore') dialog('版本操作', '正式版本保留检查、最小修复、同发布实例重建、回退与移除。变更前先展示计划，运行中的版本禁止修改。')
  if (button.classList.contains('dialog-close') || button.classList.contains('dialog-confirm')) $('#mockDialog').close()
})
$('#logSearch').addEventListener('input', renderLogs)
$('#logLevel').addEventListener('change', renderLogs)
document.addEventListener('input', event => { if (event.target.type === 'range') { appearancePreview.mask = Number(event.target.value); event.target.nextElementSibling.textContent = event.target.value + '%'; $('#app').style.setProperty('--content-mask-opacity', String(Math.max(0, (appearancePreview.mask - 62) / 100 + .02))) } })
document.addEventListener('keydown', event => { if (/input|textarea|select/i.test(event.target.tagName)) return; const map = { '1': 'home', '2': 'versions', '3': 'engines', '4': 'logs', '5': 'settings' }; if (map[event.key]) navigate(map[event.key]) })
window.addEventListener('message', event => {
  if (event.source !== parent || event.data?.type !== 'launcher-review') return
  if (event.data.page) navigate(event.data.page)
  if (event.data.state) { clearTimeout(transitionTimer); changeState(event.data.state) }
  if (event.data.setting) settingsContent(event.data.setting)
})
settingsContent(currentSetting)
navigate(currentPage)
renderState()
renderLogs()
if (currentState === 'error') addLog('service', '服务健康检查未通过，本次启动已结束。请选择查看日志或重试启动。', 'ERROR')
