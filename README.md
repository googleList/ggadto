# RankLab 模板整理版

## 目录
- `index.html`：首页（原始抓取到的 index-3 首页变体）
- `pages/`：已抓取到的 10 个内页
- `assets/css/`：统一 CSS 文件（修正 custom-animation 命名）
- `assets/js/`：统一 JS 文件（修正 custom-carousel 命名，已清理 BootstrapMB 注入的跳转/演示提示）
- `assets/images/`：合并整理后的图片资源
- `assets/fonts/`：字体目录（原始抓取包未包含字体文件）
- `assets/vendor/`：预留第三方依赖目录

## 已处理
1. 将页面整理为统一文件名，清除 `.下载` 等下载后缀。
2. 页面资源引用统一指向 `assets/css`、`assets/js` 和 `assets/images`。
3. 移除外层 BootstrapMB 预览壳、统计/预览脚本引用和反下载跳转逻辑。
4. 修复 Owl Carousel 导航箭头的错误 HTML，补充可见的箭头样式。
5. 为原始 AJAX 表单脚本提供本地安全提示，避免跳转到模板站。
6. 修正已抓取页面之间的导航链接。

## 文件检查结果
- 原始 ZIP：576 个条目，压缩包 CRC 检查通过。
- 已整理页面：11 个 HTML 文件。
- 本地 HTML 对 CSS、JS、图片的直接引用：检查后未发现缺失引用。
- JavaScript 语法：18 个 JS 文件全部通过 Node.js `--check` 语法检查。
- 注意：原始抓取资源不完整，CSS 中仍引用若干未随抓取包保存的背景图片（如 `hero-bg3.png`、`breadcumb.png`）及图标字体文件。这些属于源抓取缺失资源，无法从压缩包恢复。部分装饰背景或字体图标可能需要用原始授权源码包补齐。
- 目前完成的是文件层面检查，未在真实浏览器环境中做所有设备/所有轮播场景的视觉验收。
