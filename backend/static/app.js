const state = {
  page: 1,
  pageSize: 12,
  currentTotal: 0,
  listings: [],
  marketMedianUnitPrice: null,
  scatterRows: [],
  boxplotRows: [],
  options: null,
};

const DETAIL_CLOSE_DURATION = 160;
let detailCloseTimer = 0;

const formatNumber = (value, digits = 0) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
  return Number(value).toLocaleString("zh-CN", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
};

const apiBase = window.location.protocol === "file:" ? "http://127.0.0.1:8765" : "";

const getJson = async (url) => {
  const response = await fetch(`${apiBase}${url}`);
  if (!response.ok) throw new Error(`${url} ${response.status}`);
  return response.json();
};

const escapeHtml = (value) =>
  String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

const imageProxyUrl = (url) => (url ? `${apiBase}/api/image?url=${encodeURIComponent(url)}` : "");

const listingImageUrl = (url) => {
  if (!url) return "";
  try {
    const parsed = new URL(url);
    return parsed.hostname.includes("daojiale.com") ? url : imageProxyUrl(url);
  } catch {
    return imageProxyUrl(url);
  }
};

const placeholderImage = (item) => {
  const district = item?.district || "重庆";
  const community = item?.community || "二手房源";
  const price = item?.totalPriceWan ? `${formatNumber(item.totalPriceWan, 0)}万` : "暂无图片";
  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" width="224" height="168" viewBox="0 0 224 168">
      <defs>
        <linearGradient id="g" x1="0" x2="1" y1="0" y2="1">
          <stop offset="0" stop-color="#e7f3f0"/>
          <stop offset="1" stop-color="#d9e7f3"/>
        </linearGradient>
      </defs>
      <rect width="224" height="168" rx="12" fill="url(#g)"/>
      <path d="M42 124V73l70-42 70 42v51h-29V91h-31v33H42z" fill="#0f7b6c" opacity=".82"/>
      <rect x="56" y="88" width="22" height="21" rx="3" fill="#ffffff" opacity=".72"/>
      <rect x="91" y="88" width="22" height="21" rx="3" fill="#ffffff" opacity=".72"/>
      <text x="112" y="139" text-anchor="middle" font-size="18" font-family="Arial, Microsoft YaHei" fill="#172033" font-weight="700">${district}</text>
      <text x="112" y="157" text-anchor="middle" font-size="13" font-family="Arial, Microsoft YaHei" fill="#667085">${community.slice(0, 10)} · ${price}</text>
    </svg>
  `;
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
};

function renderMetrics(summary) {
  state.marketMedianUnitPrice = summary.medianUnitPrice;
  const metrics = [
    ["有效房源", `${formatNumber(summary.validCount)} 套`, `原始 ${formatNumber(summary.rawCount)} 条`],
    ["平均单价", `${formatNumber(summary.avgUnitPrice)} 元/㎡`, `中位数 ${formatNumber(summary.medianUnitPrice)} 元/㎡`],
    ["平均总价", `${formatNumber(summary.avgTotalPrice, 1)} 万`, `平均面积 ${formatNumber(summary.avgArea, 1)}㎡`],
    ["覆盖区县", `${formatNumber(summary.districtCount)} 个`, `${formatNumber(summary.communityCount)} 个小区`],
  ];

  document.querySelector("#metricGrid").innerHTML = metrics
    .map(
      ([label, value, note]) => `
        <article class="metric-card">
          <div class="metric-label">${label}</div>
          <div class="metric-value">${value}</div>
          <div class="metric-note">${note}</div>
        </article>
      `,
    )
    .join("");

  document.querySelector("#latestCrawlTime").textContent = summary.latestCrawlTime
    ? `采集时间 ${summary.latestCrawlTime.replace("T", " ")}`
    : "采集时间 --";
  document.querySelector("#datasetSize").textContent = `有效样本 ${formatNumber(summary.validCount)} 套`;
}

function renderBarList(containerId, rows, options = {}) {
  const container = document.querySelector(containerId);
  const valueKey = options.valueKey ?? "count";
  const labelKey = options.labelKey ?? "label";
  const limit = options.limit ?? rows.length;
  const color = options.color ?? "var(--accent)";
  const suffix = options.suffix ?? "";
  const data = rows.slice(0, limit);
  const max = Math.max(...data.map((row) => Number(row[valueKey]) || 0), 1);

  container.innerHTML = data
    .map((row) => {
      const value = Number(row[valueKey]) || 0;
      const width = Math.max(2, (value / max) * 100);
      return `
        <div class="bar-row">
          <div class="bar-label" title="${escapeHtml(row[labelKey])}">${escapeHtml(row[labelKey])}</div>
          <div class="bar-track">
            <div class="bar-fill" style="width:${width}%;background:${color}"></div>
          </div>
          <div class="bar-value">${formatNumber(value)}${suffix}</div>
        </div>
      `;
    })
    .join("");
}

function renderScatter(rows) {
  const canvas = document.querySelector("#scatterChart");
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  canvas.width = Math.max(300, Math.floor(rect.width * dpr));
  canvas.height = Math.max(240, Math.floor(rect.height * dpr));
  const ctx = canvas.getContext("2d");
  ctx.scale(dpr, dpr);
  const width = rect.width;
  const height = rect.height;
  const padding = { left: 58, right: 18, top: 18, bottom: 42 };
  const plotW = width - padding.left - padding.right;
  const plotH = height - padding.top - padding.bottom;

  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#f8fafc";
  ctx.fillRect(0, 0, width, height);

  const clean = rows.filter((row) => row.areaM2 && row.totalPriceWan);
  if (!clean.length) {
    ctx.fillStyle = "#667085";
    ctx.font = "14px Arial";
    ctx.textAlign = "center";
    ctx.fillText("暂无散点数据", width / 2, height / 2);
    return;
  }
  const maxArea = Math.min(Math.max(...clean.map((row) => row.areaM2), 1), 650);
  const maxTotalPrice = Math.min(Math.max(...clean.map((row) => row.totalPriceWan), 1), 1200);
  const palette = ["#0f7b6c", "#d36b38", "#365b9f", "#8a5a12", "#7a4db3", "#1677a3", "#b44761", "#4f7d34"];
  const districts = [...new Set(clean.map((row) => row.district))];

  ctx.strokeStyle = "#d9e1ec";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(padding.left, padding.top);
  ctx.lineTo(padding.left, height - padding.bottom);
  ctx.lineTo(width - padding.right, height - padding.bottom);
  ctx.stroke();

  ctx.fillStyle = "#667085";
  ctx.font = "12px Arial";
  ctx.textAlign = "center";
  ctx.fillText("面积㎡", padding.left + plotW / 2, height - 10);
  ctx.save();
  ctx.translate(14, padding.top + plotH / 2);
  ctx.rotate(-Math.PI / 2);
  ctx.fillText("总价 万元", 0, 0);
  ctx.restore();

  ctx.globalAlpha = 0.72;
  clean.forEach((row) => {
    const x = padding.left + (Math.min(row.areaM2, maxArea) / maxArea) * plotW;
    const y = padding.top + plotH - (Math.min(row.totalPriceWan, maxTotalPrice) / maxTotalPrice) * plotH;
    const color = palette[districts.indexOf(row.district) % palette.length];
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(x, y, 2.4, 0, Math.PI * 2);
    ctx.fill();
  });
  ctx.globalAlpha = 1;
}

function renderConclusions(items) {
  document.querySelector("#conclusions").innerHTML = items
    .map((item) => `<li>${escapeHtml(item)}</li>`)
    .join("");
}

function renderPredictionResult(data) {
  const interval = data.interval || {};
  const references = (data.references || []).slice(0, 3);
  const result = document.querySelector("#predictionResult");
  result.innerHTML = `
    <div class="prediction-hero">
      <div>
        <span>预测总价</span>
        <strong>${formatNumber(data.predictedTotalPrice, 1)}万</strong>
      </div>
      <div>
        <span>${formatNumber(data.futureMonths)}个月后单价</span>
        <strong>${formatNumber(data.predictedUnitPrice)}元/㎡</strong>
      </div>
    </div>
    <div class="prediction-metrics">
      <div>
        <span>当前估价</span>
        <strong>${formatNumber(data.currentTotalPrice, 1)}万</strong>
      </div>
      <div>
        <span>价格区间</span>
        <strong>${formatNumber(interval.lowTotalPrice, 1)}-${formatNumber(interval.highTotalPrice, 1)}万</strong>
      </div>
      <div>
        <span>年化趋势</span>
        <strong>${formatNumber(data.annualGrowthRate, 1)}%</strong>
      </div>
      <div>
        <span>置信度</span>
        <strong>${formatNumber(data.confidence, 1)}%</strong>
      </div>
    </div>
    <div class="prediction-drivers">
      ${(data.drivers || []).map((item) => `<span>${escapeHtml(item)}</span>`).join("")}
    </div>
    <div class="prediction-references">
      ${references
        .map(
          (item) => `
            <div class="reference-row">
              <strong>${escapeHtml(item.community || item.district)}</strong>
              <span>${formatNumber(item.areaM2, 1)}㎡ · ${formatNumber(item.totalPriceWan, 0)}万 · ${formatNumber(item.similarity, 1)}%</span>
            </div>
          `,
        )
        .join("")}
    </div>
  `;
}

async function runPricePrediction() {
  const form = document.querySelector("#predictionForm");
  const result = document.querySelector("#predictionResult");
  const params = new URLSearchParams(new FormData(form));
  result.innerHTML = `<div class="prediction-empty">模型计算中...</div>`;
  try {
    const data = await getJson(`/api/analysis/price-prediction?${params.toString()}`);
    renderPredictionResult(data);
  } catch (error) {
    result.innerHTML = `<div class="prediction-empty">预测失败：${escapeHtml(error.message)}</div>`;
  }
}

function renderPricePredictor(options = {}) {
  const districts = options.districts || [];
  const orientations = options.orientations || [];
  const defaultDistrict = districts.includes("九龙坡") ? "九龙坡" : districts[0] || "";
  document.querySelector("#pricePredictor").innerHTML = `
    <form id="predictionForm" class="predictor-form">
      <label>
        <span>区县</span>
        <select name="district">
          ${districts
            .map(
              (district) =>
                `<option value="${escapeHtml(district)}" ${district === defaultDistrict ? "selected" : ""}>${escapeHtml(district)}</option>`,
            )
            .join("")}
        </select>
      </label>
      <label>
        <span>小区 / 位置</span>
        <input name="location" type="text" value="华润二十四城" />
      </label>
      <label>
        <span>面积</span>
        <input name="area" type="number" min="30" max="600" step="1" value="120" />
      </label>
      <label>
        <span>室数</span>
        <input name="room" type="number" min="1" max="9" step="1" value="3" />
      </label>
      <label>
        <span>厅数</span>
        <input name="hall" type="number" min="0" max="5" step="1" value="2" />
      </label>
      <label>
        <span>朝向</span>
        <select name="orientation">
          <option value="">不限</option>
          ${orientations
            .slice(0, 16)
            .map((orientation) => `<option value="${escapeHtml(orientation)}">${escapeHtml(orientation)}</option>`)
            .join("")}
        </select>
      </label>
      <label>
        <span>预测周期</span>
        <select name="months">
          <option value="6">6个月</option>
          <option value="12" selected>12个月</option>
          <option value="24">24个月</option>
          <option value="36">36个月</option>
          <option value="60">60个月</option>
        </select>
      </label>
      <button type="submit">开始预测</button>
    </form>
    <div id="predictionResult" class="prediction-result"></div>
  `;

  document.querySelector("#predictionForm").addEventListener("submit", (event) => {
    event.preventDefault();
    runPricePrediction();
  });
  runPricePrediction();
}

function renderMarketSegments(rows) {
  document.querySelector("#marketSegments").innerHTML = rows
    .map((row) => `
      <div class="segment-card">
        <div class="segment-title">${escapeHtml(row.label)}</div>
        <div class="segment-count">${formatNumber(row.count)} 套</div>
        <div class="segment-meta">
          <span>${formatNumber(row.share, 1)}%</span>
          <span>${formatNumber(row.avgUnitPrice)}元/㎡</span>
          <span>${formatNumber(row.avgTotalPrice, 1)}万</span>
        </div>
      </div>
    `)
    .join("");
}

function renderInsightTable(containerId, columns, rows) {
  document.querySelector(containerId).innerHTML = `
    <div class="table-head">
      ${columns.map((column) => `<span>${escapeHtml(column.label)}</span>`).join("")}
    </div>
    ${rows
      .map(
        (row) => `
          <div class="table-row">
            ${columns.map((column) => `<span>${escapeHtml(column.render(row))}</span>`).join("")}
          </div>
        `,
      )
      .join("")}
  `;
}

function renderCorrelations(rows) {
  document.querySelector("#correlationPanel").innerHTML = rows
    .map((row) => {
      const coefficient = Number(row.coefficient) || 0;
      const width = Math.max(4, Math.min(100, Math.abs(coefficient) * 100));
      const color = coefficient >= 0 ? "var(--accent)" : "var(--accent-2)";
      return `
        <div class="correlation-row">
          <div class="correlation-name">
            <strong>${escapeHtml(row.label)}</strong>
            <span>${escapeHtml(row.strength)}</span>
          </div>
          <div class="correlation-track">
            <div class="correlation-fill" style="width:${width}%;background:${color}"></div>
          </div>
          <div class="correlation-value">${formatNumber(row.coefficient, 3)}</div>
        </div>
      `;
    })
    .join("");
}

function renderDistrictRoomHeatmap(data) {
  const container = document.querySelector("#districtRoomHeatmap");
  const districts = data.districts || [];
  const roomLabels = data.roomLabels || [];
  const cells = data.cells || [];
  if (!districts.length || !roomLabels.length || !cells.length) {
    container.innerHTML = `<div class="empty-state">暂无户型热力数据</div>`;
    return;
  }

  const maxCount = Math.max(...cells.map((cell) => Number(cell.count) || 0), 1);
  const byKey = new Map(cells.map((cell) => [`${cell.district}-${cell.roomLabel}`, cell]));
  const columnStyle = `grid-template-columns: 86px repeat(${roomLabels.length}, minmax(68px, 1fr))`;

  container.innerHTML = `
    <div class="heatmap-grid" style="${columnStyle}">
      <div class="heatmap-corner">区县</div>
      ${roomLabels.map((label) => `<div class="heatmap-head">${escapeHtml(label)}</div>`).join("")}
      ${districts
        .map((district) => {
          const rowCells = roomLabels
            .map((label) => {
              const cell = byKey.get(`${district}-${label}`) || {};
              const count = Number(cell.count) || 0;
              const alpha = count ? 0.12 + (count / maxCount) * 0.78 : 0.04;
              return `
                <div class="heatmap-cell" style="background:rgba(15, 123, 108, ${alpha})" title="${escapeHtml(district)} ${escapeHtml(label)}">
                  <strong>${formatNumber(count)}</strong>
                  <span>${cell.avgUnitPrice ? `${formatNumber(cell.avgUnitPrice)}元/㎡` : "--"}</span>
                </div>
              `;
            })
            .join("");
          return `<div class="heatmap-district">${escapeHtml(district)}</div>${rowCells}`;
        })
        .join("")}
    </div>
  `;
}

function renderUnitPriceBoxplot(rows) {
  const canvas = document.querySelector("#unitPriceBoxplotChart");
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  canvas.width = Math.max(320, Math.floor(rect.width * dpr));
  canvas.height = Math.max(300, Math.floor(rect.height * dpr));
  const ctx = canvas.getContext("2d");
  ctx.scale(dpr, dpr);
  const width = rect.width;
  const height = rect.height;
  const padding = { left: 76, right: 24, top: 22, bottom: 42 };
  const plotW = width - padding.left - padding.right;
  const plotH = height - padding.top - padding.bottom;

  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#f8fafc";
  ctx.fillRect(0, 0, width, height);

  const clean = rows.filter(
    (row) => row.p10 !== null && row.q1 !== null && row.median !== null && row.q3 !== null && row.p90 !== null,
  );
  if (!clean.length) {
    ctx.fillStyle = "#667085";
    ctx.font = "14px Arial";
    ctx.textAlign = "center";
    ctx.fillText("暂无箱线图数据", width / 2, height / 2);
    return;
  }

  const minValue = Math.min(...clean.map((row) => row.p10));
  const maxValue = Math.max(...clean.map((row) => row.p90));
  const floor = Math.max(0, Math.floor(minValue / 1000) * 1000);
  const ceiling = Math.ceil(maxValue / 1000) * 1000;
  const range = Math.max(1, ceiling - floor);
  const rowGap = plotH / clean.length;
  const boxHeight = Math.min(18, Math.max(10, rowGap * 0.48));
  const xOf = (value) => padding.left + ((value - floor) / range) * plotW;

  ctx.strokeStyle = "#d9e1ec";
  ctx.lineWidth = 1;
  ctx.fillStyle = "#667085";
  ctx.font = "12px Arial";
  ctx.textAlign = "center";
  const tickCount = 4;
  for (let index = 0; index <= tickCount; index += 1) {
    const value = floor + (range / tickCount) * index;
    const x = xOf(value);
    ctx.beginPath();
    ctx.moveTo(x, padding.top);
    ctx.lineTo(x, padding.top + plotH);
    ctx.stroke();
    ctx.fillText(`${formatNumber(value / 10000, 1)}万`, x, height - 16);
  }

  clean.forEach((row, index) => {
    const y = padding.top + rowGap * index + rowGap / 2;
    const p10 = xOf(row.p10);
    const q1 = xOf(row.q1);
    const med = xOf(row.median);
    const q3 = xOf(row.q3);
    const p90 = xOf(row.p90);

    ctx.strokeStyle = "#365b9f";
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(p10, y);
    ctx.lineTo(p90, y);
    ctx.moveTo(p10, y - boxHeight * 0.45);
    ctx.lineTo(p10, y + boxHeight * 0.45);
    ctx.moveTo(p90, y - boxHeight * 0.45);
    ctx.lineTo(p90, y + boxHeight * 0.45);
    ctx.stroke();

    ctx.fillStyle = "rgba(15, 123, 108, 0.2)";
    ctx.strokeStyle = "#0f7b6c";
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.roundRect(q1, y - boxHeight / 2, Math.max(2, q3 - q1), boxHeight, 4);
    ctx.fill();
    ctx.stroke();

    ctx.strokeStyle = "#d36b38";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(med, y - boxHeight * 0.62);
    ctx.lineTo(med, y + boxHeight * 0.62);
    ctx.stroke();

    ctx.fillStyle = "#172033";
    ctx.font = "12px Arial, Microsoft YaHei";
    ctx.textAlign = "right";
    ctx.fillText(row.district, padding.left - 10, y + 4);
    ctx.fillStyle = "#667085";
    ctx.textAlign = "left";
    ctx.fillText(`${formatNumber(row.median)}元/㎡`, Math.min(width - 78, p90 + 8), y + 4);
  });

  ctx.fillStyle = "#667085";
  ctx.font = "12px Arial, Microsoft YaHei";
  ctx.textAlign = "center";
  ctx.fillText("单价区间（p10 / q1 / 中位数 / q3 / p90）", padding.left + plotW / 2, height - 2);
}

function sourceLabel(source) {
  const text = String(source || "").toLowerCase();
  if (text.includes("daojiale")) return "到家了";
  if (text.includes("fang")) return "房天下";
  return source || "未标注";
}

function classifyListing(item) {
  const totalPrice = Number(item.totalPriceWan) || 0;
  const area = Number(item.areaM2) || 0;
  const unitPrice = Number(item.unitPriceYuanM2) || 0;
  if (totalPrice >= 500 || area >= 200) return "高端大宅";
  if (unitPrice >= 20000) return "核心高价";
  if (area >= 110 && totalPrice >= 100) return "改善居住";
  if (totalPrice < 100 || area < 90) return "刚需紧凑";
  return "主流均衡";
}

function unitPriceLevel(item) {
  const unitPrice = Number(item.unitPriceYuanM2);
  const median = Number(state.marketMedianUnitPrice);
  if (!unitPrice || !median) return "市场对比 --";
  const delta = (unitPrice - median) / median;
  if (delta >= 0.25) return "高于市场中位";
  if (delta <= -0.15) return "低于市场中位";
  return "接近市场中位";
}

function formatDateTime(value) {
  if (!value) return "--";
  return String(value).replace("T", " ").slice(0, 19);
}

function renderDetailMetric(label, value, note = "") {
  return `
    <div class="detail-metric">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
      ${note ? `<small>${escapeHtml(note)}</small>` : ""}
    </div>
  `;
}

function renderDetailRow(label, value) {
  return `
    <div class="detail-row">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value || "--")}</strong>
    </div>
  `;
}

function closeListingDetail() {
  const layer = document.querySelector("#listingDetailLayer");
  if (!layer || layer.hidden) return;

  window.clearTimeout(detailCloseTimer);
  document.body.classList.remove("detail-open");
  document.querySelectorAll(".listing-card.is-selected").forEach((card) => card.classList.remove("is-selected"));

  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    layer.hidden = true;
    layer.classList.remove("is-closing");
    return;
  }

  layer.classList.add("is-closing");
  detailCloseTimer = window.setTimeout(() => {
    layer.hidden = true;
    layer.classList.remove("is-closing");
    detailCloseTimer = 0;
  }, DETAIL_CLOSE_DURATION);
}

function isListingDetailOpen() {
  const layer = document.querySelector("#listingDetailLayer");
  return Boolean(layer && !layer.hidden);
}

function isEventInsideListingDetail(event) {
  const dialog = document.querySelector("#listingDetailDialog");
  const target = event.target;
  return Boolean(dialog && target && dialog.contains(target));
}

function closeListingDetailFromOutsideScroll(event) {
  if (!isListingDetailOpen() || isEventInsideListingDetail(event)) return;
  closeListingDetail();
}

function getListingColumnIndex(card, grid, columnCount) {
  const cardCenter = card.getBoundingClientRect().left + card.getBoundingClientRect().width / 2;
  const firstRowCards = [...grid.querySelectorAll(".listing-card")].slice(0, columnCount);
  if (!firstRowCards.length) return 1;
  let bestIndex = 1;
  let bestDistance = Number.POSITIVE_INFINITY;
  firstRowCards.forEach((candidate, index) => {
    const rect = candidate.getBoundingClientRect();
    const center = rect.left + rect.width / 2;
    const distance = Math.abs(center - cardCenter);
    if (distance < bestDistance) {
      bestDistance = distance;
      bestIndex = index + 1;
    }
  });
  return bestIndex;
}

function positionListingDetail(card) {
  const layer = document.querySelector("#listingDetailLayer");
  const dialog = document.querySelector("#listingDetailDialog");
  const grid = document.querySelector("#listingGrid");
  if (!layer || !dialog || !card || !grid) return;

  dialog.style.left = "";
  dialog.style.right = "";
  dialog.style.top = "";
  dialog.style.bottom = "";
  dialog.style.width = "";
  dialog.style.maxHeight = "";
  dialog.classList.remove("detail-left");

  if (window.matchMedia("(max-width: 760px)").matches) return;

  const columnCount = Math.max(1, getComputedStyle(grid).gridTemplateColumns.split(" ").filter(Boolean).length);
  const columnIndex = getListingColumnIndex(card, grid, columnCount);
  const openLeft = columnCount >= 3 ? columnIndex === columnCount : columnCount === 2 ? columnIndex === 2 : false;
  const cardRect = card.getBoundingClientRect();
  const gap = 14;
  const padding = 12;
  const width = Math.min(460, Math.max(390, Math.floor(window.innerWidth * 0.28)));
  const maxHeight = Math.min(640, window.innerHeight - padding * 2);

  let left = openLeft ? cardRect.left - width - gap : cardRect.right + gap;
  left = Math.max(padding, Math.min(window.innerWidth - width - padding, left));
  let top = cardRect.top;
  top = Math.max(padding, Math.min(window.innerHeight - maxHeight - padding, top));

  dialog.style.width = `${width}px`;
  dialog.style.left = `${left}px`;
  dialog.style.top = `${top}px`;
  dialog.style.maxHeight = `${maxHeight}px`;
  dialog.classList.toggle("detail-left", openLeft);
}

function openListingDetail(item, card) {
  const layer = document.querySelector("#listingDetailLayer");
  const dialog = document.querySelector("#listingDetailDialog");
  if (!item || !layer || !dialog || !card) return;

  window.clearTimeout(detailCloseTimer);
  detailCloseTimer = 0;
  layer.classList.remove("is-closing");

  const imageSrc = listingImageUrl(item.coverImageUrl) || placeholderImage(item);
  const fallback = placeholderImage(item);
  const tags = (item.tags || []).slice(0, 8).map((tag) => `<span class="tag">${escapeHtml(tag)}</span>`).join("");
  const roomHall = item.roomCount || item.hallCount ? `${formatNumber(item.roomCount)}室 ${formatNumber(item.hallCount)}厅` : "--";

  dialog.innerHTML = `
    <button class="detail-close" type="button" aria-label="关闭详情">×</button>
    <img class="detail-hero" src="${escapeHtml(imageSrc)}" data-fallback="${escapeHtml(fallback)}" alt="${escapeHtml(item.community || item.title)}" />
    <div class="detail-body">
      <div class="detail-source">
        <span>${escapeHtml(sourceLabel(item.source))}</span>
        ${item.isNew ? "<strong>新上</strong>" : ""}
        ${item.sourceListingId ? `<em>ID ${escapeHtml(item.sourceListingId)}</em>` : ""}
      </div>
      <div class="detail-heading">
        <h3>${escapeHtml(item.title || item.community || "房源详情")}</h3>
        <span class="detail-badge">${escapeHtml(classifyListing(item))}</span>
      </div>
      <div class="detail-metrics">
        ${renderDetailMetric("总价", `${formatNumber(item.totalPriceWan, 0)}万`, "挂牌总价")}
        ${renderDetailMetric("单价", `${formatNumber(item.unitPriceYuanM2)}元/㎡`, unitPriceLevel(item))}
        ${renderDetailMetric("面积", `${formatNumber(item.areaM2, 1)}㎡`, "建筑面积")}
      </div>
      <div class="detail-row-grid">
        ${renderDetailRow("区域", item.district)}
        ${renderDetailRow("小区", item.community)}
        ${renderDetailRow("户型", item.layout)}
        ${renderDetailRow("室厅", roomHall)}
        ${renderDetailRow("朝向", item.orientation)}
        ${renderDetailRow("来源", sourceLabel(item.source))}
        ${renderDetailRow("页码", item.page ? `第 ${formatNumber(item.page)} 页` : "--")}
        ${renderDetailRow("采集时间", formatDateTime(item.crawlTime))}
      </div>
      <div class="detail-tags">${tags || '<span class="tag">暂无标签</span>'}</div>
    </div>
  `;

  document.querySelectorAll(".listing-card.is-selected").forEach((selected) => selected.classList.remove("is-selected"));
  card.classList.add("is-selected");
  layer.hidden = false;
  document.body.classList.add("detail-open");
  positionListingDetail(card);

  dialog.querySelector(".detail-close")?.addEventListener("click", closeListingDetail);
  const detailImage = dialog.querySelector(".detail-hero");
  detailImage?.addEventListener(
    "error",
    () => {
      detailImage.src = detailImage.dataset.fallback;
      detailImage.classList.add("listing-image-fallback");
    },
    { once: true },
  );
}

function initListingDetailLayer() {
  const grid = document.querySelector("#listingGrid");
  const layer = document.querySelector("#listingDetailLayer");
  if (!grid || !layer) return;

  const openFromCard = (card) => {
    if (isListingDetailOpen() && card.classList.contains("is-selected")) {
      closeListingDetail();
      return;
    }

    const index = Number(card.dataset.listingIndex);
    openListingDetail(state.listings[index], card);
  };

  grid.addEventListener("click", (event) => {
    const card = event.target.closest(".listing-card");
    if (!card) return;
    openFromCard(card);
  });

  grid.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    const card = event.target.closest(".listing-card");
    if (!card) return;
    event.preventDefault();
    openFromCard(card);
  });

  layer.addEventListener("click", (event) => {
    if (event.target === layer) closeListingDetail();
  });

  document.addEventListener("click", (event) => {
    const dialog = document.querySelector("#listingDetailDialog");
    if (layer.hidden || dialog?.contains(event.target) || event.target.closest(".listing-card")) return;
    closeListingDetail();
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeListingDetail();
  });

  document.addEventListener("wheel", closeListingDetailFromOutsideScroll, { passive: true });
  document.addEventListener("touchmove", closeListingDetailFromOutsideScroll, { passive: true });
  window.addEventListener("scroll", () => {
    if (isListingDetailOpen()) closeListingDetail();
  });

  window.addEventListener("resize", () => {
    const selected = document.querySelector(".listing-card.is-selected");
    if (!layer.hidden && selected) positionListingDetail(selected);
  });
}

function listingQuery() {
  const params = new URLSearchParams();
  const district = document.querySelector("#districtFilter").value;
  const keyword = document.querySelector("#keywordFilter").value.trim();
  const minPrice = document.querySelector("#minPriceFilter").value;
  const maxPrice = document.querySelector("#maxPriceFilter").value;
  const sort = document.querySelector("#sortFilter").value;

  params.set("page", state.page);
  params.set("page_size", state.pageSize);
  params.set("sort", sort);
  if (district) params.set("district", district);
  if (keyword) params.set("keyword", keyword);
  if (minPrice) params.set("min_price", minPrice);
  if (maxPrice) params.set("max_price", maxPrice);
  return params.toString();
}

async function loadListings() {
  const data = await getJson(`/api/houses?${listingQuery()}`);
  closeListingDetail();
  state.listings = data.items || [];
  state.currentTotal = data.total;
  const totalPages = Math.max(1, Math.ceil(data.total / data.pageSize));
  document.querySelector("#listingTotal").textContent = `共 ${formatNumber(data.total)} 套`;
  document.querySelector("#pageInfo").textContent = `${data.page} / ${totalPages}`;
  document.querySelector("#prevPage").disabled = data.page <= 1;
  document.querySelector("#nextPage").disabled = data.page >= totalPages;

  document.querySelector("#listingGrid").innerHTML = state.listings
    .map((item, index) => {
      const tags = (item.tags || []).slice(0, 3).map((tag) => `<span class="tag">${escapeHtml(tag)}</span>`).join("");
      const imageSrc = listingImageUrl(item.coverImageUrl) || placeholderImage(item);
      const fallback = placeholderImage(item);
      return `
        <article class="listing-card" role="button" tabindex="0" data-listing-index="${index}" aria-label="查看房源详情">
          <img class="listing-image" src="${escapeHtml(imageSrc)}" data-fallback="${escapeHtml(fallback)}" alt="${escapeHtml(item.community || item.title)}" loading="lazy" />
          <div>
            <h3 title="${escapeHtml(item.title)}">${escapeHtml(item.title)}</h3>
            <div class="listing-meta">
              <span>${escapeHtml(item.district)}</span>
              <span>${escapeHtml(item.community || "未知小区")}</span>
              <span>${escapeHtml(item.layout || "--")}</span>
              <span>${formatNumber(item.areaM2, 1)}㎡</span>
            </div>
            <div class="listing-price">${formatNumber(item.totalPriceWan, 0)}万 · ${formatNumber(item.unitPriceYuanM2)}元/㎡</div>
            <div class="tag-list">${tags}</div>
          </div>
        </article>
      `;
    })
    .join("");

  document.querySelectorAll(".listing-image").forEach((image) => {
    image.addEventListener(
      "error",
      () => {
        image.src = image.dataset.fallback;
        image.classList.add("listing-image-fallback");
      },
      { once: true },
    );
  });
}

async function initFilters() {
  const options = await getJson("/api/options");
  state.options = options;
  const select = document.querySelector("#districtFilter");
  select.innerHTML = `<option value="">全部区县</option>${options.districts
    .map((district) => `<option value="${escapeHtml(district)}">${escapeHtml(district)}</option>`)
    .join("")}`;

  document.querySelector("#searchButton").addEventListener("click", () => {
    state.page = 1;
    loadListings();
  });
  document.querySelector("#prevPage").addEventListener("click", () => {
    state.page = Math.max(1, state.page - 1);
    loadListings();
  });
  document.querySelector("#nextPage").addEventListener("click", () => {
    state.page += 1;
    loadListings();
  });
}

async function initDashboard() {
  const [
    summary,
    districts,
    priceDistribution,
    areaDistribution,
    roomLayout,
    scatter,
    conclusions,
    marketSegments,
    districtQuadrants,
    topCommunities,
    tags,
    orientations,
    correlations,
    districtRoomHeatmap,
    unitPriceBoxplot,
  ] =
    await Promise.all([
      getJson("/api/summary"),
      getJson("/api/stats/districts"),
      getJson("/api/stats/price-distribution"),
      getJson("/api/stats/area-distribution"),
      getJson("/api/stats/room-layout"),
      getJson("/api/stats/scatter?limit=1400"),
      getJson("/api/analysis/conclusions"),
      getJson("/api/analysis/market-segments"),
      getJson("/api/analysis/district-quadrants"),
      getJson("/api/analysis/top-communities"),
      getJson("/api/stats/tags"),
      getJson("/api/stats/orientations"),
      getJson("/api/analysis/correlations"),
      getJson("/api/stats/district-room-heatmap"),
      getJson("/api/stats/district-unit-price-boxplot"),
    ]);

  state.scatterRows = scatter;
  state.boxplotRows = unitPriceBoxplot;
  renderMetrics(summary);
  renderBarList(
    "#districtPriceChart",
    districts.filter((row) => row.count >= 50),
    {
      labelKey: "district",
      valueKey: "avgUnitPrice",
      suffix: "",
      limit: 12,
      color: "linear-gradient(90deg, var(--accent-3), #6b8ee8)",
    },
  );
  renderBarList("#priceDistributionChart", priceDistribution, {
    valueKey: "count",
    color: "linear-gradient(90deg, var(--accent-2), #e8a075)",
  });
  renderBarList("#areaDistributionChart", areaDistribution, {
    valueKey: "count",
    color: "linear-gradient(90deg, var(--accent), #55b6a9)",
  });
  renderBarList(
    "#roomChart",
    roomLayout.map((row) => ({ label: `${row.roomCount}室`, count: row.count })),
    { valueKey: "count", color: "linear-gradient(90deg, #8a5a12, #d8a54f)" },
  );
  renderScatter(scatter);
  renderConclusions(conclusions);
  renderPricePredictor(state.options || {});
  renderMarketSegments(marketSegments);
  renderInsightTable(
    "#districtQuadrants",
    [
      { label: "区县", render: (row) => row.district },
      { label: "象限", render: (row) => row.quadrant },
      { label: "样本", render: (row) => `${formatNumber(row.count)}套` },
      { label: "均价", render: (row) => `${formatNumber(row.avgUnitPrice)}元/㎡` },
    ],
    districtQuadrants.slice(0, 12),
  );
  renderInsightTable(
    "#topCommunities",
    [
      { label: "小区", render: (row) => row.community },
      { label: "区县", render: (row) => row.district },
      { label: "样本", render: (row) => `${formatNumber(row.count)}套` },
      { label: "均价", render: (row) => `${formatNumber(row.avgUnitPrice)}元/㎡` },
    ],
    topCommunities.slice(0, 12),
  );
  renderBarList("#tagChart", tags, {
    valueKey: "count",
    limit: 10,
    color: "linear-gradient(90deg, #7a4db3, #b69bea)",
  });
  renderBarList("#orientationChart", orientations, {
    valueKey: "count",
    limit: 10,
    color: "linear-gradient(90deg, #1677a3, #72bdd9)",
  });
  renderCorrelations(correlations);
  renderDistrictRoomHeatmap(districtRoomHeatmap);
  renderUnitPriceBoxplot(unitPriceBoxplot);
}

async function main() {
  await initFilters();
  await initDashboard();
  initListingDetailLayer();
  await loadListings();
  window.addEventListener("resize", () => {
    renderScatter(state.scatterRows);
    renderUnitPriceBoxplot(state.boxplotRows);
  });
}

main().catch((error) => {
  document.body.innerHTML = `<main class="panel"><h1>加载失败</h1><p>${escapeHtml(error.message)}</p></main>`;
});
