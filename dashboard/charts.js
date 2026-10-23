/* Chart rendering for the case viewer. One Chart.js line chart per panel.
   Solid line = observed up to the slider step ("Now"); dashed = later points. */
(function () {
  const COLORS = {
    creatinine: '#c0392b', bun: '#e9a84c', urine_output: '#2a9d8f', lactate: '#7b6fa0',
    map: '#c0392b', hr: '#e9a84c', cvp: '#2a9d8f',
    iv_fluids: '#5c7a8a', vasopressors: '#7b6fa0', egfr: '#c0392b',
  };

  let charts = {};        // {labs,vitals,fluid,vaso,egfr}
  let theCase = null;
  let labels = [];
  let akiLabels = [];
  let step = 0;

  const nowLinePlugin = {
    id: 'nowLine',
    afterDraw(chart) {
      const s = chart._nowStep;
      if (s === undefined) return;
      const { ctx, chartArea, scales } = chart;
      const x = scales.x.getPixelForValue(s);
      ctx.save();
      ctx.beginPath();
      ctx.strokeStyle = 'rgba(42,157,143,.9)';
      ctx.lineWidth = 1.5;
      ctx.setLineDash([5, 3]);
      ctx.moveTo(x, chartArea.top);
      ctx.lineTo(x, chartArea.bottom);
      ctx.stroke();
      ctx.setLineDash([]);
      const label = labels[s] || '';
      ctx.font = '600 9px ' + getComputedStyle(document.body).getPropertyValue('--mono');
      const tw = ctx.measureText(label).width;
      const bw = tw + 10, bh = 13, bx = x - bw / 2, by = chartArea.top - bh;
      ctx.fillStyle = 'rgba(42,157,143,.14)';
      ctx.fillRect(bx, by, bw, bh);
      ctx.strokeStyle = 'rgba(42,157,143,.45)';
      ctx.strokeRect(bx, by, bw, bh);
      ctx.fillStyle = '#1a7a70';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(label, x, by + bh / 2);
      ctx.restore();
    },
  };

  const akiLabelPlugin = {
    id: 'akiLabels',
    afterDraw(chart) {
      if (!chart._isEgfr) return;
      const { ctx, chartArea, scales } = chart;
      ctx.save();
      ctx.font = '600 8.5px ' + getComputedStyle(document.body).getPropertyValue('--mono');
      ctx.textAlign = 'center';
      ctx.fillStyle = '#e9a84c';
      akiLabels.forEach(function (label, i) {
        const x = scales.x.getPixelForValue(i);
        ctx.fillText(label, x, chartArea.top - 6);
      });
      ctx.restore();
    },
  };

  Chart.register(nowLinePlugin, akiLabelPlugin);

  function baseOptions(extraPlugins) {
    return {
      responsive: true, maintainAspectRatio: false,
      animation: { duration: 250 },
      layout: { padding: { top: 22 } },
      scales: {
        x: { title: { display: true, text: 'Time', font: { size: 10 } }, ticks: { font: { size: 10 } }, grid: { color: '#f0f0f0' } },
        y: { ticks: { font: { size: 10 } }, grid: { color: '#f0f0f0' } },
      },
      plugins: Object.assign({
        legend: { display: false },
        tooltip: { callbacks: { title: function (items) { return labels[items[0].dataIndex] || ''; } } },
        nowLine: { clip: false },
      }, extraPlugins || {}),
    };
  }

  function seriesFor(category, key) {
    const s = theCase.series;
    if (category === 'labs') return s.labs[key];
    if (category === 'vitals') return s.vitals[key];
    if (category === 'fluid') return s.iv_fluids;
    if (category === 'vaso') return s.vasopressors;
    if (category === 'egfr') return s.egfr;
    return null;
  }

  function colorKey(category, key) {
    if (category === 'fluid') return 'iv_fluids';
    if (category === 'vaso') return 'vasopressors';
    if (category === 'egfr') return 'egfr';
    return key;
  }

  function render(category, key) {
    const chart = charts[category];
    const cfg = seriesFor(category, key);
    if (!chart || !cfg) return;
    const color = COLORS[colorKey(category, key)] || '#2a9d8f';
    chart._nowStep = step;
    const solid = cfg.data.map(function (v, i) { return i <= step ? v : null; });
    const future = cfg.data.map(function (v, i) { return i >= step ? v : null; });
    chart.data = {
      labels: labels,
      datasets: [
        {
          data: solid, borderColor: color, backgroundColor: color + '18', borderWidth: 2.5,
          tension: .35, fill: true, spanGaps: false,
          pointRadius: solid.map(function (v, i) { return v !== null ? (i === step ? 6 : 4) : 0; }),
          pointBackgroundColor: solid.map(function (v, i) { return i === step ? '#fff' : color; }),
          pointBorderColor: color,
          pointBorderWidth: solid.map(function (v, i) { return i === step ? 2.5 : 0; }),
        },
        {
          data: future, borderColor: color + '38', backgroundColor: 'transparent',
          borderWidth: 1.5, borderDash: [4, 4], tension: .35, pointRadius: 0, fill: false, spanGaps: false,
        },
      ],
    };
    chart.options.scales.y.title = { display: true, text: cfg.unit, font: { size: 10 } };
    chart.update();
  }

  function currentKey(category) {
    if (category === 'labs') return document.getElementById('labsSelect').value;
    if (category === 'vitals') return document.getElementById('vitalsSelect').value;
    return category;
  }

  function renderAll() {
    ['labs', 'vitals', 'fluid', 'vaso', 'egfr'].forEach(function (c) { render(c, currentKey(c)); });
  }

  const Charts = {
    init() {
      charts.labs = new Chart(document.getElementById('labsChart'), { type: 'line', data: {}, options: baseOptions() });
      charts.vitals = new Chart(document.getElementById('vitalsChart'), { type: 'line', data: {}, options: baseOptions() });
      charts.fluid = new Chart(document.getElementById('fluidChart'), { type: 'line', data: {}, options: baseOptions() });
      charts.vaso = new Chart(document.getElementById('vasoChart'), { type: 'line', data: {}, options: baseOptions() });
      charts.egfr = new Chart(document.getElementById('egfrChart'), { type: 'line', data: {}, options: baseOptions({ akiLabels: {} }) });
      charts.egfr._isEgfr = true;
    },
    setCase(caseObj) {
      theCase = caseObj;
      labels = caseObj.timeline.labels;
      akiLabels = caseObj.timeline.aki_stage_labels || [];
      step = labels.length - 1;
      renderAll();
    },
    setStep(s) { step = s; renderAll(); },
    renderCategory(category) { render(category, currentKey(category)); },
    get step() { return step; },
    get labels() { return labels; },
  };

  window.Charts = Charts;
})();
