import { useEffect, useMemo, useState } from "react";

const numberFormatter = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 0,
});

const decimalFormatter = new Intl.NumberFormat("en-US", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

function formatValue(value, format) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }

  if (format === "percent") {
    return `${decimalFormatter.format(value)}%`;
  }

  return numberFormatter.format(value);
}

function buildQuery(params) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      query.set(key, value);
    }
  });
  return query.toString();
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function calculateEma(points, period = 12) {
  const alpha = 2 / (period + 1);
  let previous = null;

  return points.map((point) => {
    previous = previous === null ? point.value : point.value * alpha + previous * (1 - alpha);
    return { ...point, ema: previous };
  });
}

function EmptyState({ title, body }) {
  return (
    <div className="empty-state">
      <h3>{title}</h3>
      <p>{body}</p>
    </div>
  );
}

function LineChart({ points, format, metricLabel }) {
  const cleanPoints = points.filter((point) => typeof point.value === "number");
  const [hoveredIndex, setHoveredIndex] = useState(null);
  const [tooltip, setTooltip] = useState(null);
  const emaPoints = useMemo(() => calculateEma(cleanPoints), [cleanPoints]);

  if (cleanPoints.length === 0) {
    return (
      <EmptyState
        title="No series data"
        body="Adjust the metric, state, or date range to load weekly observations."
      />
    );
  }

  const width = 960;
  const height = 320;
  const padding = { top: 18, right: 18, bottom: 44, left: 70 };
  const values = emaPoints.flatMap((point) => [point.value, point.ema]);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;

  const xFor = (index) =>
    padding.left +
    (index / Math.max(emaPoints.length - 1, 1)) * (width - padding.left - padding.right);
  const yFor = (value) =>
    height -
    padding.bottom -
    ((value - min) / range) * (height - padding.top - padding.bottom);

  const linePath = emaPoints
    .map((point, index) => `${index === 0 ? "M" : "L"} ${xFor(index)} ${yFor(point.value)}`)
    .join(" ");
  const emaPath = emaPoints
    .map((point, index) => `${index === 0 ? "M" : "L"} ${xFor(index)} ${yFor(point.ema)}`)
    .join(" ");
  const areaPath = `${linePath} L ${xFor(emaPoints.length - 1)} ${
    height - padding.bottom
  } L ${xFor(0)} ${height - padding.bottom} Z`;

  const latestPoint = emaPoints[emaPoints.length - 1];
  const yTicks = Array.from({ length: 4 }, (_, index) => {
    const ratio = index / 3;
    const value = max - range * ratio;
    return { value, y: yFor(value) };
  });
  const xLabels = [
    emaPoints[0],
    emaPoints[Math.floor(emaPoints.length / 2)],
    emaPoints[emaPoints.length - 1],
  ];
  const activeIndex = hoveredIndex ?? emaPoints.length - 1;
  const activePoint = emaPoints[activeIndex];

  function handleMouseMove(event) {
    const rect = event.currentTarget.getBoundingClientRect();
    const relativeX = ((event.clientX - rect.left) / rect.width) * width;
    const boundedX = clamp(relativeX, padding.left, width - padding.right);
    const ratio = (boundedX - padding.left) / (width - padding.left - padding.right);
    const index = Math.round(ratio * Math.max(emaPoints.length - 1, 1));
    const point = emaPoints[index];
    const left = (xFor(index) / width) * rect.width;
    const top = (Math.min(yFor(point.value), yFor(point.ema)) / height) * rect.height;

    setHoveredIndex(index);
    setTooltip({
      left,
      top,
      alignRight: left > rect.width - 220,
    });
  }

  function handleMouseLeave() {
    setHoveredIndex(null);
    setTooltip(null);
  }

  return (
    <div className="chart-shell">
      <div className="chart-header">
        <div>
          <h3>{metricLabel}</h3>
          <p className="section-subtitle">Weekly values with a 12-week exponential moving average.</p>
        </div>
        <div className="chart-meta">
          <p className="chart-latest">
            Latest: <strong>{formatValue(latestPoint.value, format)}</strong>
          </p>
          <div className="chart-legend" aria-hidden="true">
            <span className="legend-swatch legend-swatch--value" />
            <span>Weekly</span>
            <span className="legend-swatch legend-swatch--ema" />
            <span>12-week EMA</span>
          </div>
        </div>
      </div>
      <svg
        className="chart"
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={metricLabel}
        onMouseMove={handleMouseMove}
        onMouseLeave={handleMouseLeave}
      >
        <defs>
          <linearGradient id="lineFill" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="rgba(101, 221, 186, 0.32)" />
            <stop offset="100%" stopColor="rgba(101, 221, 186, 0)" />
          </linearGradient>
        </defs>

        {yTicks.map((tick) => (
          <g key={tick.y}>
            <line
              className="chart-grid"
              x1={padding.left}
              x2={width - padding.right}
              y1={tick.y}
              y2={tick.y}
            />
            <text className="chart-axis" x={padding.left - 12} y={tick.y + 4} textAnchor="end">
              {formatValue(tick.value, format)}
            </text>
          </g>
        ))}

        <path d={areaPath} fill="url(#lineFill)" />
        <path className="chart-line" d={linePath} />
        <path className="chart-line chart-line--ema" d={emaPath} />
        <circle
          className="chart-point"
          cx={xFor(emaPoints.length - 1)}
          cy={yFor(latestPoint.value)}
          r="5"
        />
        {hoveredIndex !== null ? (
          <>
            <line
              className="chart-crosshair"
              x1={xFor(activeIndex)}
              x2={xFor(activeIndex)}
              y1={padding.top}
              y2={height - padding.bottom}
            />
            <circle
              className="chart-point chart-point--active"
              cx={xFor(activeIndex)}
              cy={yFor(activePoint.value)}
              r="6"
            />
            <circle
              className="chart-point chart-point--ema"
              cx={xFor(activeIndex)}
              cy={yFor(activePoint.ema)}
              r="5"
            />
          </>
        ) : null}

        {xLabels.map((point, index) => (
          <text
            key={`${point.startDate}-${index}`}
            className="chart-axis"
            x={xFor(emaPoints.indexOf(point))}
            y={height - 12}
            textAnchor={index === 0 ? "start" : index === xLabels.length - 1 ? "end" : "middle"}
          >
            {point.startDate}
          </text>
        ))}
      </svg>
      {tooltip ? (
        <div
          className={`chart-tooltip${tooltip.alignRight ? " chart-tooltip--right" : ""}`}
          style={{ left: `${tooltip.left}px`, top: `${tooltip.top}px` }}
        >
          <p>{activePoint.startDate}</p>
          <strong>{formatValue(activePoint.value, format)}</strong>
          <span>12-week EMA: {formatValue(activePoint.ema, format)}</span>
        </div>
      ) : null}
    </div>
  );
}

function RecordsTable({ rows, metrics }) {
  if (!rows.length) {
    return (
      <EmptyState
        title="No rows returned"
        body="The current filters do not match any records in the weekly state feed."
      />
    );
  }

  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Week</th>
            <th>Start</th>
            <th>End</th>
            <th>State</th>
            {metrics.map((metric) => (
              <th key={metric.id}>{metric.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={`${row.entityCode}-${row.year}-${row.week}`}>
              <td>
                {row.year}-W{String(row.week).padStart(2, "0")}
              </td>
              <td>{row.startDate}</td>
              <td>{row.endDate}</td>
              <td>{row.entityName}</td>
              {metrics.map((metric) => (
                <td key={metric.id}>{formatValue(row[metric.id], metric.format)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function App() {
  const [metadata, setMetadata] = useState(null);
  const [filters, setFilters] = useState({
    metric: "BA_NSA",
    entity: "CA",
    startDate: "",
    endDate: "",
  });
  const [series, setSeries] = useState(null);
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();

    async function loadMetadata() {
      try {
        const response = await fetch("/api/metadata", { signal: controller.signal });
        if (!response.ok) {
          throw new Error("Failed to load metadata");
        }
        const payload = await response.json();
        setMetadata(payload);
        setFilters((current) => ({
          ...current,
          entity: payload.dataset.defaultEntity,
          startDate: payload.dateRange.start,
          endDate: payload.dateRange.end,
        }));
      } catch (err) {
        if (err.name !== "AbortError") {
          setError(err.message);
        }
      }
    }

    loadMetadata();
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!metadata) {
      return;
    }

    const controller = new AbortController();
    setLoading(true);
    setError("");

    async function loadData() {
      try {
        const params = {
          entity: filters.entity,
          start_date: filters.startDate,
          end_date: filters.endDate,
        };

        const [seriesResponse, recordsResponse] = await Promise.all([
          fetch(`/api/series?${buildQuery({ ...params, metric: filters.metric })}`, {
            signal: controller.signal,
          }),
          fetch(`/api/records?${buildQuery({ ...params, limit: 104 })}`, {
            signal: controller.signal,
          }),
        ]);

        if (!seriesResponse.ok || !recordsResponse.ok) {
          throw new Error("Failed to load state data");
        }

        const [seriesPayload, recordsPayload] = await Promise.all([
          seriesResponse.json(),
          recordsResponse.json(),
        ]);

        setSeries(seriesPayload);
        setRecords(recordsPayload.rows);
      } catch (err) {
        if (err.name !== "AbortError") {
          setError(err.message);
          setSeries(null);
          setRecords([]);
        }
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      }
    }

    loadData();
    return () => controller.abort();
  }, [metadata, filters]);

  const metricOptions = metadata?.metrics ?? [];
  const stateOptions = metadata?.dataset?.entities ?? [];
  const downloadUrl = metadata
    ? `/api/download?${buildQuery({
        entity: filters.entity,
        start_date: filters.startDate,
        end_date: filters.endDate,
      })}`
    : "";

  return (
    <div className="page-shell">
      <main className="layout">
        <header className="page-header">
          <div>
            <h1>State Business Formation Statistics</h1>
            <p className="page-intro">
              Explore the live Census weekly state applications feed and download the
              filtered rows shown in this view.
            </p>
          </div>
          <button
            className="download-button"
            type="button"
            disabled={!downloadUrl}
            onClick={() => {
              window.location.assign(downloadUrl);
            }}
          >
            Download CSV
          </button>
        </header>

        <section className="panel controls-panel">
          <div className="section-header">
            <div>
              <h2>Filters</h2>
              <p className="section-subtitle">Choose a state, metric, and date range.</p>
            </div>
            {loading ? <span className="status-chip">Refreshing data</span> : null}
          </div>

          <div className="controls-grid controls-grid--state">
            <label>
              State
              <select
                value={filters.entity}
                onChange={(event) =>
                  setFilters((current) => ({ ...current, entity: event.target.value }))
                }
              >
                {stateOptions.map((entity) => (
                  <option key={entity.value} value={entity.value}>
                    {entity.label}
                  </option>
                ))}
              </select>
            </label>

            <label>
              Metric
              <select
                value={filters.metric}
                onChange={(event) =>
                  setFilters((current) => ({ ...current, metric: event.target.value }))
                }
              >
                {metricOptions.map((metric) => (
                  <option key={metric.id} value={metric.id}>
                    {metric.label}
                  </option>
                ))}
              </select>
            </label>

            <label>
              Start date
              <input
                type="date"
                min={metadata?.dateRange.start}
                max={filters.endDate || metadata?.dateRange.end}
                value={filters.startDate}
                onChange={(event) =>
                  setFilters((current) => ({ ...current, startDate: event.target.value }))
                }
              />
            </label>

            <label>
              End date
              <input
                type="date"
                min={filters.startDate || metadata?.dateRange.start}
                max={metadata?.dateRange.end}
                value={filters.endDate}
                onChange={(event) =>
                  setFilters((current) => ({ ...current, endDate: event.target.value }))
                }
              />
            </label>
          </div>
        </section>

        {error ? (
          <section className="panel">
            <EmptyState title="Viewer error" body={error} />
          </section>
        ) : null}

        {series ? (
          <>
            <section className="panel">
              <div className="section-header section-header--top">
                <div>
                  <h2>{series.entityName}</h2>
                  <p className="section-subtitle">{series.metricLabel}</p>
                </div>
                <dl className="stat-list">
                  <div>
                    <dt>Latest</dt>
                    <dd>{formatValue(series.summary.latestValue, series.metricFormat)}</dd>
                  </div>
                  <div>
                    <dt>Average</dt>
                    <dd>{formatValue(series.summary.average, series.metricFormat)}</dd>
                  </div>
                  <div>
                    <dt>Minimum</dt>
                    <dd>{formatValue(series.summary.minimum, series.metricFormat)}</dd>
                  </div>
                  <div>
                    <dt>Maximum</dt>
                    <dd>{formatValue(series.summary.maximum, series.metricFormat)}</dd>
                  </div>
                </dl>
              </div>

              <div className="content-grid">
                <LineChart
                  points={series.points}
                  format={series.metricFormat}
                  metricLabel={`${series.entityName} · ${series.metricLabel}`}
                />

                <aside className="detail-panel">
                  <h3>Current selection</h3>
                  <dl>
                    <div>
                      <dt>Source</dt>
                      <dd>Live Census weekly CSV</dd>
                    </div>
                    <div>
                      <dt>Metric</dt>
                      <dd>{series.metricLabel}</dd>
                    </div>
                    <div>
                      <dt>Latest week</dt>
                      <dd>{series.summary.latestWindow || "—"}</dd>
                    </div>
                    <div>
                      <dt>Observed points</dt>
                      <dd>{numberFormatter.format(series.summary.pointCount)}</dd>
                    </div>
                  </dl>
                </aside>
              </div>
            </section>

            <section className="panel">
              <div className="section-header">
                <div>
                  <h2>Underlying rows</h2>
                  <p className="section-subtitle">Most recent 104 weeks for the current filter set.</p>
                </div>
              </div>
              <RecordsTable rows={records} metrics={metricOptions} />
            </section>
          </>
        ) : null}
      </main>
    </div>
  );
}
