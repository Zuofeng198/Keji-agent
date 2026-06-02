# 环形图 Hover 放大动画 Bug 排查与修复记录

## 问题描述

统计页面的 Canvas 环形图（donut chart）实现了 hover 交互：鼠标移到扇区上，该扇区会平滑放大（外径 +6px，内径 -2.4px），移开后缩小还原。

但存在一个顽固 Bug：**快速移入移出鼠标时，扇区保持放大状态不缩小，只有再次移入才恢复正常。**

## 排查过程

### 第一版：状态机方案

最初用 `_hoverAnim` 对象记录动画状态：

```javascript
_hoverAnim = {
  toIdx: target,       // 目标扇区索引
  fromIdx: source,     // 来源扇区索引
  initExpand: 0..1,    // 出口动画的初始展开量
  progress: 0..1,      // 动画进度（ease-out 后）
  t0: timestamp,
  duration: 180
}
```

入口动画：`expandAmt = progress * 6`
出口动画：`expandAmt = (1 - progress) * initExpand * 6`

#### Bug 1：initExpand 双重 ease-out

出口动画需要记录入口动画被打断时的当前展开量。错误地用了：

```javascript
initExpand = 1 - Math.pow(1 - prev.progress, 3);  // ❌ 二次 ease-out
```

但 `prev.progress` **已经是** ease-out 后的值了（`progress = 1 - (1-t)³`）。再套一次 ease-out 得到的值比实际大，导致出口动画第一帧的 expandAmt 比入口最后一帧大，视觉上扇区"弹跳"一下才缩小。

**修复**：直接取 `initExpand = prev.progress`。

#### Bug 2：handler 提前清除了 _hoverIdx

出口动画依赖 `_hoverIdx` 来渲染展开效果：

```javascript
var actualHover = canvas._hoverIdx;   // 动画引擎驱动这个值
var expandAmt = canvas._currentExpand;
```

但 handler 在"不在圆环内"分支直接设了 `_hoverIdx = -1`：

```javascript
// onDonutHover — ❌ 错误做法
if (dist > outerR) {
  c._hoverIdx = -1;           // 扇区立刻失去"选中"状态
  _startDonutAnim(c, -1);     // 启动出口动画
}
```

出口动画启动时 `_hoverIdx` 已是 -1，`actualHover = -1`，没有扇区匹配，`expandAmt` 再大也不生效。扇区瞬间 snap 到 0px，但下一帧 `_currentExpand` 才开始缩小，用户看到的是"瞬间消失但动画值还在跑"，感觉就像卡住了。

**修复**：handler 不再碰 `_hoverIdx`，全权交给动画引擎管理。出口动画在 `t < 1` 期间保留 `_hoverIdx` 不变，`t >= 1` 才清为 -1。

### 第二版：简单 lerp 方案

废弃状态机，改用单值追踪：

```javascript
canvas._currentExpand   // 当前的展开 px 值（0~6）
canvas._animTarget      // 目标扇区索引（>=0）或 -1（出口）
canvas._animStart       // 动画开始时间戳
```

每帧逻辑简化为两行：

```javascript
var targetVal = _animTarget >= 0 ? 6 : 0;           // 目标值
_currentExpand += (targetVal - _currentExpand) * e;  // lerp 到目标
```

优势：
- 无状态机，无 `fromIdx`/`toIdx`/`initExpand` 等复杂变量
- 入口/出口/中断/重新进入都走同一公式，不留分支死角
- `_currentExpand` 永远代表当前真实展开量，任何时刻中断都能平滑过渡

## 最终代码结构

```
动画引擎
├── _startDonutAnim(canvas, targetIdx)
│   └── 设置 _animTarget、记录时间、调用 _donutTick
├── _donutTick(canvas)
│   ├── 计算 ease-out 进度
│   ├── lerp _currentExpand 到目标值
│   ├── 管理 _hoverIdx（出口期间锁定，完成后清为 -1）
│   └── requestAnimationFrame 循环
└── drawDonutChart(total, hoverIdx)
    ├── expandAmt = canvas._currentExpand || 0
    └── actualHover = canvas._hoverIdx

鼠标事件 handler
├── onDonutHover(e)
│   ├── 不在环内 → _startDonutAnim(c, -1)，不碰 _hoverIdx
│   ├── 未命中扇区 → 同上
│   └── 命中扇区 → _startDonutAnim(c, found)
├── onDonutLeave(e)
│   └── _startDonutAnim(c, -1)（如果 _animTarget 不是 -1）
```

## 教训

1. **状态机的状态太多时，每个分支都要验证** — `toIdx`/`fromIdx`/`initExpand`/`progress` 四个变量组合出大量状态路径，容易遗漏。
2. **handler 和引擎不要竞争同一个变量** — `_hoverIdx` 被两边同时写入，引擎的控制权不纯粹，导致时序问题。
3. **Canvas 动画的平滑中断** — 用 lerp 而不是根据目标计算绝对值，天然支持任意时刻中断和反转。
