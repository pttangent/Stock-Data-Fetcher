import React, { useEffect, useRef } from 'react';
import { createChart, ColorType, CandlestickSeries, HistogramSeries, IChartApi, Time } from 'lightweight-charts';
import type { OHLCVBar } from "@workspace/api-client-react";

export interface CandlestickChartProps {
  data: OHLCVBar[];
  interval: string;
}

export default function CandlestickChart({ data, interval }: CandlestickChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!chartContainerRef.current) return;

    const containerEl = chartContainerRef.current;

    const chart = createChart(containerEl, {
      layout: {
        background: { type: ColorType.Solid, color: "#09090b" },
        textColor: "#a1a1aa",
      },
      grid: {
        vertLines: { color: "#27272a" },
        horzLines: { color: "#27272a" },
      },
      width: containerEl.clientWidth,
      height: 400,
      timeScale: { timeVisible: true, secondsVisible: false },
    });
    
    chartRef.current = chart;

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#22c55e",
      downColor: "#ef4444",
      borderUpColor: "#22c55e",
      borderDownColor: "#ef4444",
      wickUpColor: "#22c55e",
      wickDownColor: "#ef4444",
    });

    const volSeries = chart.addSeries(HistogramSeries, {
      color: "#3f3f46",
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
    });
    chart.priceScale("volume").applyOptions({ scaleMargins: { top: 0.7, bottom: 0 } });

    // Format data
    const validData = data.filter(d => 
      d.open !== null && d.high !== null && d.low !== null && d.close !== null
    );

    const sortedData = [...validData].sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime());

    const candleData = sortedData.map(d => ({
      time: (new Date(d.date).getTime() / 1000) as Time,
      open: d.open!,
      high: d.high!,
      low: d.low!,
      close: d.close!
    }));

    const volumeData = sortedData.map(d => ({
      time: (new Date(d.date).getTime() / 1000) as Time,
      value: d.volume || 0,
      color: d.close! >= d.open! ? "#22c55e80" : "#ef444480"
    }));

    candleSeries.setData(candleData);
    volSeries.setData(volumeData);

    const resizeObserver = new ResizeObserver(entries => {
      if (entries.length === 0 || entries[0].target !== chartContainerRef.current) return;
      const newRect = entries[0].contentRect;
      chart.applyOptions({ width: newRect.width });
    });

    resizeObserver.observe(chartContainerRef.current);

    return () => {
      resizeObserver.disconnect();
      chart.remove();
    };
  }, [data]);

  return (
    <div className="w-full">
      <div ref={chartContainerRef} className="w-full h-[400px]" />
    </div>
  );
}
