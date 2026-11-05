/**
 * 招聘页右下角的悬浮按钮：「＋ 收录到简历通」。
 *
 * 支持的两种浏览形态：
 * 1. 独立详情页（地址是 /job_detail/…）：直接拿 location.href；
 * 2. BOSS 的**分栏视图**（地址仍是 /web/geek/jobs?query=…）：读"当前选中的卡片"
 *    （`.job-card-wrap.active a.job-name` 的 href），那才是用户正看着的岗位。
 *
 * 为什么不是"扩展后台直接调本机接口"：这套 Chromium（156）对**命令行加载**的扩展
 * 只注册、不唤醒 Service Worker——`chrome.runtime.connect` 直接报
 * "Receiving end does not exist."。页面自己 fetch 本机又会被混合内容拦掉。
 * 所以走"开一个很小的一次性窗口 → 应用导入完用 postMessage 回应 → 窗口自关"：
 * 主页面不跳走、后台留不下标签页，同时还能把"导入成功/失败"回写到按钮上。
 */
(() => {
  if (document.getElementById("resumeforge-capture")) return;

  // 上游架构由后端直接提供前端页面：1.x 在 8005，2.0 独立实例在 8010（同源 dist）。
  const APP_ORIGIN = "http://127.0.0.1:8010";

  // 原样带上完整地址：BOSS 的 securityId 是打开详情页所必需的；应用负责入库前规范化。
  const resolveJobUrl = () => {
    if (location.pathname.startsWith("/job_detail/")) return location.href;
    const active = document.querySelector(
      'li.job-card-wrap.active a.job-name[href*="/job_detail/"], ' +
        '.job-card-wrap.active a.job-name[href*="/job_detail/"]',
    );
    const href = active?.getAttribute("href") || "";
    return href ? new URL(href, location.origin).href : "";
  };

  const box = document.createElement("div");
  box.id = "resumeforge-capture";
  box.style.cssText = [
    "position:fixed",
    "right:24px",
    "bottom:170px",
    "z-index:2147483000",
    "display:flex",
    "flex-direction:column",
    "align-items:flex-end",
    "gap:6px",
    "font:13px/1.4 system-ui,-apple-system,'Microsoft YaHei',sans-serif",
  ].join(";");

  const button = document.createElement("button");
  button.type = "button";
  button.textContent = "＋ 收录到简历通";
  button.style.cssText = [
    "padding:9px 14px",
    "border:0",
    "border-radius:18px",
    "background:#1f4e79",
    "color:#fff",
    "font-size:13px",
    "cursor:pointer",
    "box-shadow:0 4px 14px rgba(31,78,121,.35)",
  ].join(";");

  const status = document.createElement("div");
  status.style.cssText = [
    "max-width:280px",
    "padding:6px 10px",
    "border-radius:8px",
    "background:rgba(0,0,0,.75)",
    "color:#fff",
    "display:none",
    "word-break:break-all",
  ].join(";");

  const showStatus = (text, ok) => {
    status.textContent = text;
    status.style.background = ok ? "rgba(22,101,52,.92)" : "rgba(153,27,27,.92)";
    status.style.display = "block";
    if (ok) {
      const open = document.createElement("a");
      open.textContent = " 去岗位广场看看 →";
      open.href = "#";
      open.style.cssText = "color:#fff;text-decoration:underline;margin-left:4px";
      open.addEventListener("click", (event) => {
        event.preventDefault();
        window.open(APP_ORIGIN + "/jobs", "_blank");
      });
      status.appendChild(open);
    }
  };

  const showWaiting = (text) => {
    status.textContent = text;
    status.style.background = "rgba(31,78,121,.92)";
    status.style.display = "block";
  };

  let pendingTimer = 0;
  const armTimeout = (ms, text) => {
    clearTimeout(pendingTimer);
    pendingTimer = setTimeout(() => {
      button.disabled = false;
      button.textContent = "＋ 收录到简历通";
      showStatus(text, false);
    }, ms);
  };

  window.addEventListener("message", (event) => {
    const data = event.data;
    if (!data) return;
    // 应用弹窗一加载就发这个：说明窗口连上了，导入慢是在等招聘站，不是在瞎等。
    if (data.type === "resumeforge-import-started") {
      armTimeout(
        120000,
        "导入仍在进行：招聘网站响应较慢，请稍后再看结果（" + APP_ORIGIN + "）",
      );
      showWaiting("已连接本地服务，正在导入…");
      return;
    }
    if (data.type !== "resumeforge-import-result") return;
    clearTimeout(pendingTimer);
    button.disabled = false;
    if (data.ok) {
      button.textContent = "✓ 已收录";
      showStatus(`已收录「${data.title || "该岗位"}」到岗位广场`, true);
    } else {
      button.textContent = "＋ 收录到简历通";
      showStatus(data.error || "收录失败：请确认简历通已启动", false);
    }
  });

  button.addEventListener("click", () => {
    const url = resolveJobUrl();
    if (!url) {
      showStatus("没找到当前岗位：先在左边列表里点一个岗位，再点收录", false);
      return;
    }
    button.disabled = true;
    button.textContent = "收录中…";
    const target =
      APP_ORIGIN + "/jobs?close_after=1&import_url=" + encodeURIComponent(url);
    // 每次用唯一窗口名：如果当前页恰好叫 resumeforge-import（上一个弹窗被导航到这里），
    // 固定名字会让 window.open 把当前页自己导航走，应用回执后的 close 会关掉老板的招聘页。
    const windowName = "resumeforge-import-" + Date.now();
    const popup = window.open(target, windowName, "width=460,height=560");
    window.focus();
    if (!popup || popup === window) {
      button.disabled = false;
      button.textContent = "＋ 收录到简历通";
      showStatus("浏览器拦截了弹窗：请允许本页弹窗后重试", false);
      return;
    }
    // 先等两件事之一：窗口连上的 started 回执（12 秒），或最终结果。
    // 收到 started 后把上限放宽到 120 秒（招聘站慢时导入本身就可能几十秒）。
    armTimeout(
      12000,
      "导入窗口没有回应：请确认简历通已启动，或稍后重试（" + APP_ORIGIN + "）",
    );
  });

  box.append(status, button);
  document.body.appendChild(box);
})();
