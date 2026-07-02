const state = {
  page: 1,
  pageSize: 12,
  currentTotal: 0,
};

const formatNumber = (value, digits = 0) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
  return Number(value).toLocaleString("zh-CN", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
};

const getJson = async (url) => {
  const response = await fetch(url);
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

const imageProxyUrl = (url) => (url ? `/api/image?url=${encodeURIComponent(url)}` : "");

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

function renderDistrictRoomHeatmap(data) {
  const container = document.querySelector("#districtRoomHeatmap");
  const districts = data?.districts || [];
  const roomLabels = data?.roomLabels || [];
  const cells = data?.cells || [];
  if (!districts.length || !roomLabels.length) {
    container.innerHTML = `<div class="empty-state">暂无热力图数据</div>`;
    return;
  }

  const cellMap = new Map(cells.map((cell) => [`${cell.district}__${cell.roomLabel}`, cell]));
  const maxPrice = Math.max(...cells.map((cell) => Number(cell.avgUnitPrice) || 0), 1);
  const minPrice = Math.min(...cells.filter((cell) => cell.avgUnitPrice).map((cell) => Number(cell.avgUnitPrice)), maxPrice);
  const priceRange = Math.max(maxPrice - minPrice, 1);

  const colorFor = (value) => {
    if (!value) return "rgba(237, 241, 247, 0.88)";
    const ratio = Math.max(0.08, Math.min(1, (Number(value) - minPrice) / priceRange));
    return `rgba(15, 123, 108, ${0.18 + ratio * 0.72})`;
  };

  container.style.setProperty("--heatmap-cols", roomLabels.length + 1);
  container.innerHTML = `
    <div class="heatmap-head heatmap-corner">区县</div>
    ${roomLabels.map((label) => `<div class="heatmap-head">${escapeHtml(label)}</div>`).join("")}
    ${districts
      .map((district) => {
        const rowCells = roomLabels
          .map((label) => {
            const cell = cellMap.get(`${district}__${label}`) || {};
            const price = cell.avgUnitPrice;
            return `
              <div class="heatmap-cell" style="background:${colorFor(price)}" title="${escapeHtml(district)} ${escapeHtml(label)}：${formatNumber(price)}元/㎡，${formatNumber(cell.count || 0)}套">
                <strong>${formatNumber(price)}</strong>
                <span>${formatNumber(cell.count || 0)}套</span>
              </div>
            `;
          })
          .join("");
        return `<div class="heatmap-label">${escapeHtml(district)}</div>${rowCells}`;
      })
      .join("")}
  `;
}

function renderConclusions(items) {
  document.querySelector("#conclusions").innerHTML = items
    .map((item) => `<li>${escapeHtml(item)}</li>`)
    .join("");
}

function renderValueDistricts(rows) {
  const topRows = rows.slice(0, 8);
  const maxScore = Math.max(...topRows.map((row) => row.valueScore || 0), 1);
  document.querySelector("#valueDistricts").innerHTML = `
    <div class="value-explain">
      <strong>性价比指数</strong>
      <span>综合区县平均单价与样本供给量，分数越高表示价格更友好且可选房源更充足。</span>
    </div>
    <div class="value-list">
      ${topRows
        .map((row) => {
          const width = Math.max(4, (row.valueScore / maxScore) * 100);
          return `
            <div class="value-row">
              <div class="value-main">
                <strong>${escapeHtml(row.district)}</strong>
                <span>${escapeHtml(row.level)} · ${formatNumber(row.count)}套</span>
              </div>
              <div class="value-track">
                <div class="value-fill" style="width:${width}%"></div>
              </div>
              <div class="value-score">${formatNumber(row.valueScore, 1)}</div>
              <div class="value-meta">${formatNumber(row.avgUnitPrice)}元/㎡ · ${formatNumber(row.avgTotalPrice, 1)}万</div>
            </div>
          `;
        })
        .join("")}
    </div>
  `;
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
  state.currentTotal = data.total;
  const totalPages = Math.max(1, Math.ceil(data.total / data.pageSize));
  document.querySelector("#listingTotal").textContent = `共 ${formatNumber(data.total)} 套`;
  document.querySelector("#pageInfo").textContent = `${data.page} / ${totalPages}`;
  document.querySelector("#prevPage").disabled = data.page <= 1;
  document.querySelector("#nextPage").disabled = data.page >= totalPages;

  document.querySelector("#listingGrid").innerHTML = data.items
    .map((item) => {
      const tags = (item.tags || []).slice(0, 3).map((tag) => `<span class="tag">${escapeHtml(tag)}</span>`).join("");
      const imageSrc = imageProxyUrl(item.coverImageUrl) || placeholderImage(item);
      const fallback = placeholderImage(item);
      return `
        <article class="listing-card">
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
    districtRoomHeatmap,
    scatter,
    conclusions,
    valueDistricts,
    marketSegments,
    districtQuadrants,
    topCommunities,
    tags,
    orientations,
    correlations,
  ] =
    await Promise.all([
      getJson("/api/summary"),
      getJson("/api/stats/districts"),
      getJson("/api/stats/price-distribution"),
      getJson("/api/stats/area-distribution"),
      getJson("/api/stats/room-layout"),
      getJson("/api/stats/district-room-heatmap"),
      getJson("/api/stats/scatter?limit=1400"),
      getJson("/api/analysis/conclusions"),
      getJson("/api/analysis/value-districts"),
      getJson("/api/analysis/market-segments"),
      getJson("/api/analysis/district-quadrants"),
      getJson("/api/analysis/top-communities"),
      getJson("/api/stats/tags"),
      getJson("/api/stats/orientations"),
      getJson("/api/analysis/correlations"),
    ]);

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
  renderDistrictRoomHeatmap(districtRoomHeatmap);
  renderConclusions(conclusions);
  renderValueDistricts(valueDistricts);
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
}

async function main() {
  await initFilters();
  await initDashboard();
  await loadListings();
  window.addEventListener("resize", async () => {
    const scatter = await getJson("/api/stats/scatter?limit=1400");
    renderScatter(scatter);
  });
}

main().catch((error) => {
  document.body.innerHTML = `<main class="panel"><h1>加载失败</h1><p>${escapeHtml(error.message)}</p></main>`;
});
