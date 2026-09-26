import React, { useCallback, useEffect, useRef, useState } from 'react';
import FeedCard from './FeedCard';

const GAP = 16;
const SPEED = 0.021; // px per ms — slow, continuous drift
const REDUCED_SPEED = 0.006;

function cardWidthFor(stageWidth) {
  return stageWidth >= 640 ? 236 : Math.min(250, Math.round(stageWidth * 0.72));
}

/**
 * Horizontally drifting feed. Cards enter on the right and leave on the left;
 * the card nearest the centre is fully prominent, cards towards the edges fade,
 * shrink slightly and blur a little. Positions update in requestAnimationFrame
 * via refs; React only re-renders when a card is recycled.
 */
export default function DisasterFeed({ items, running }) {
  const stageRef = useRef(null);
  const lane = useRef([]); // [{ key, itemIndex, x }] ordered left -> right
  const nodes = useRef(new Map());
  const nextKey = useRef(0);
  const nextItem = useRef(0);
  const [cardWidth, setCardWidth] = useState(236);
  const [, setVersion] = useState(0);

  const newSlot = (x) => ({ key: nextKey.current++, itemIndex: nextItem.current++ % items.length, x });

  const rebuild = useCallback((stageWidth) => {
    const cw = cardWidthFor(stageWidth);
    const step = cw + GAP;
    const count = Math.ceil(stageWidth / step) + 2;
    lane.current = Array.from({ length: count }, (_, i) => newSlot(i * step));
    setCardWidth(cw);
    setVersion((v) => v + 1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items.length]);

  useEffect(() => {
    const stage = stageRef.current;
    if (!stage || !items.length) return undefined;
    rebuild(stage.clientWidth);
    let lastWidth = stage.clientWidth;
    const ro = new ResizeObserver(() => {
      if (Math.abs(stage.clientWidth - lastWidth) > 8) {
        lastWidth = stage.clientWidth;
        rebuild(lastWidth);
      }
    });
    ro.observe(stage);
    return () => ro.disconnect();
  }, [items.length, rebuild]);

  useEffect(() => {
    if (!running || !items.length) return undefined;
    const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    const speed = reduced ? REDUCED_SPEED : SPEED;
    let raf;
    let last = 0;

    const tick = (ts) => {
      const stage = stageRef.current;
      const dt = last ? Math.min(ts - last, 50) : 16;
      last = ts;
      if (stage && lane.current.length) {
        const W = stage.clientWidth;
        const centre = W / 2;
        const step = cardWidth + GAP;
        for (const slot of lane.current) slot.x -= dt * speed;

        if (lane.current[0].x < -step) {
          const tail = lane.current[lane.current.length - 1];
          lane.current = [...lane.current.slice(1), newSlot(tail.x + step)];
          setVersion((v) => v + 1);
        }

        for (const slot of lane.current) {
          const el = nodes.current.get(slot.key);
          if (!el) continue;
          const dist = Math.min(Math.abs(slot.x + cardWidth / 2 - centre) / (W / 2), 1);
          const blur = Math.max(0, dist - 0.55) * 2.2; // at most ~1px at the edges
          el.style.transform = `translateX(${slot.x}px) scale(${1 - dist * 0.1})`;
          el.style.opacity = (1 - dist * 0.8).toFixed(3);
          el.style.filter = blur > 0.05 ? `blur(${blur.toFixed(2)}px)` : 'none';
          el.style.borderColor = dist < 0.18 ? '#a1a1aa' : '#e4e4e7';
        }
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [running, cardWidth, items.length]);

  return (
    <div ref={stageRef} className="landing-stage" aria-label="Replay of classified disaster posts" role="region">
      {lane.current.map((slot) => (
        <FeedCard
          key={slot.key}
          item={items[slot.itemIndex]}
          width={cardWidth}
          ref={(el) => {
            if (el) {
              nodes.current.set(slot.key, el);
              el.style.transform = `translateX(${slot.x}px)`;
            } else {
              nodes.current.delete(slot.key);
            }
          }}
        />
      ))}
    </div>
  );
}
