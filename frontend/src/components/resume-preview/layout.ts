import { A4_WIDTH_PX, columnsCss } from "./config";
import {
  measureResumeLayout,
  pagesNeededFor,
  type LayoutMeasure,
} from "../../utils/resumeLayoutMeasure";

export interface FrameLayoutResult {
  measure: LayoutMeasure | null;
  overflow: boolean;
  naturalWidth: number;
  pagesNeeded: number;
  visualPages: number;
  scale: number;
}

interface Options {
  document: Document;
  pageCount: number;
  paperHeight: number;
}

/**
 * 测量 iframe 并把需要的多页列数固定下来。
 *
 * 测量一定发生在单列状态，避免 columns 把纵向高度折叠后让页数看起来变少；测量完成后再
 * 写入固定 column-count。这样内容实际需要两页时，渲染列数、外层纸张宽度和虚线数量始终
 * 来自同一个 pagesNeeded，而不会再通过 scrollWidth 猜出第四页。
 */
export function layoutFrame({
  document,
  pageCount,
  paperHeight,
}: Options): FrameLayoutResult | null {
  const body = document.body;
  const root = document.documentElement;
  if (!body || !root) return null;

  body.style.width = "";
  body.style.height = "";
  const style =
    (document.getElementById("resume-preview-style") as HTMLStyleElement | null) ??
    document.createElement("style");
  style.id = "resume-preview-style";
  style.textContent = "";
  if (!style.parentElement) document.head.appendChild(style);

  const measured = measureResumeLayout(document, pageCount);
  const reportedScale = Number(body.dataset.scale ?? "");
  const templateScriptRan = Number.isFinite(reportedScale) && reportedScale > 0;

  let overflow = body.dataset.overflow === "1";
  if (!templateScriptRan) {
    const contentWidth = Math.max(body.scrollWidth, root.scrollWidth, A4_WIDTH_PX);
    const contentHeight = Math.max(body.scrollHeight, root.scrollHeight, paperHeight);
    const contentScale = Math.min(1, A4_WIDTH_PX / contentWidth, paperHeight / contentHeight);
    if (contentScale < 1) body.style.setProperty("--fit-scale", contentScale.toFixed(4));
    overflow = overflow || body.scrollHeight > paperHeight + 1;
  }

  const pagesNeeded = measured ? pagesNeededFor(measured) : overflow ? pageCount + 1 : pageCount;
  overflow = overflow || pagesNeeded > pageCount;
  // 什么时候切成横向多栏（CSS columns）：**只在用户主动选了多页时**。
  //
  // 这里曾写成 `pageCount > 1 || overflow`，于是「选了 1 页但内容超出」也会被切成
  // 左右两栏。那对用户是个误导：他选的是 1 页，看到的却是并排两张纸，像是"简历被
  // 分隔开了"；而且换任何更松的版式（舒展、换模板）都会触发，看起来像随机坏掉。
  // 溢出本身已经有明确的黄色提示与超出量数字，那才是用户该看到的信号；
  // 并排多栏只在"我就是要 2/3 页"时才有意义。
  const useColumns = pageCount > 1;
  const visualPages = useColumns ? Math.max(pageCount, pagesNeeded) : 1;
  style.textContent = useColumns ? columnsCss(visualPages) : "html,body{overflow:hidden!important}";

  // 令 columns 真正参与布局；宽度不再用于反推页数，只作为画布尺寸。
  if (useColumns) void body.offsetWidth;
  const naturalWidth = useColumns ? A4_WIDTH_PX * visualPages : A4_WIDTH_PX;

  return {
    measure: measured,
    overflow,
    naturalWidth,
    pagesNeeded,
    visualPages,
    scale: templateScriptRan ? reportedScale : 1,
  };
}
