"use client";

const WINDY_SRC =
  "https://embed.windy.com/embed2.html?lat=17.68&lon=83.33&detailLat=17.68&detailLon=83.33" +
  "&width=100%25&height=500&zoom=8&level=surface&overlay=wind&menu=&message=true&marker=" +
  "&calendar=&pressure=&type=map&location=coordinates&detail=&metricWind=default" +
  "&metricTemp=default&radarRange=-1";

export default function WindyMap() {
  return (
    <section className="rounded-xl border border-line bg-panel/40 p-5">
      <h2 className="text-sm font-semibold uppercase tracking-[0.14em] text-accent">
        Live Wind &amp; Ocean Map
      </h2>
      <p className="mt-0.5 text-xs text-slate-500">Animated wind field, centered on Visakhapatnam</p>

      <div className="mt-4 overflow-hidden rounded-lg border border-line">
        <iframe
          title="Live animated wind map, Visakhapatnam"
          src={WINDY_SRC}
          className="h-[500px] w-full"
          style={{ border: 0 }}
          loading="lazy"
        />
      </div>

      <p className="mt-2 text-center text-[11px] text-slate-600">
        Animated wind field · Windy.com
      </p>
      <p className="mt-1 text-center text-[10px] text-slate-600">
        Live map requires internet; conditions panel above uses cached values when offline.
      </p>
    </section>
  );
}
