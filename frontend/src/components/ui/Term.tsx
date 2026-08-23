/**
 * Term — zkratka nebo odborný pojem s vysvětlivkou.
 *
 * Vysvětlivka se ukazuje při najetí myší, při zaostření klávesnicí
 * i po klepnutí prstem. Atribut `title` by byl levnější, ale objeví se
 * až po vteřině, nedá se přečíst na dotykovém displeji a nejde
 * naformátovat — u pojmu, podle kterého se rozhoduje o penězích,
 * to nestačí.
 *
 * Bublina se vykresluje portálem do <body> a pozicuje se napevno.
 * Uvnitř listu s `overflow: hidden` by se jinak ořízla přesně tam,
 * kde je jí nejvíc potřeba — u posledního řádku tabulky.
 */

import React, {
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
} from 'react';
import { createPortal } from 'react-dom';
import { GLOSSARY } from '../../lib/glossary';

interface TermProps {
  /** Klíč do glosáře v src/lib/glossary.ts. */
  id: string;
  /** Zobrazený text. Bez něj se použije zkratka z glosáře. */
  children?: React.ReactNode;
  className?: string;
}

interface Placement {
  left: number;
  top: number;
  /** Bublina se vešla dolů, nebo se musela překlopit nahoru. */
  above: boolean;
}

const WIDTH = 288;
const GAP = 8;
const EDGE = 12;

export const Term: React.FC<TermProps> = ({ id, children, className = '' }) => {
  const entry = GLOSSARY[id];
  const [open, setOpen] = useState(false);
  const [place, setPlace] = useState<Placement | null>(null);
  const anchorRef = useRef<HTMLButtonElement>(null);
  const tipId = useId();

  const position = useCallback(() => {
    const anchor = anchorRef.current;
    if (!anchor) return;
    const rect = anchor.getBoundingClientRect();

    // Vodorovně vystředit na pojem, ale nepřetéct okno.
    const half = WIDTH / 2;
    const wanted = rect.left + rect.width / 2 - half;
    const left = Math.min(
      Math.max(EDGE, wanted),
      Math.max(EDGE, window.innerWidth - WIDTH - EDGE),
    );

    // Pod pojem, pokud tam je místo; jinak nad něj.
    const roomBelow = window.innerHeight - rect.bottom;
    const above = roomBelow < 140 && rect.top > 140;
    const top = above ? rect.top - GAP : rect.bottom + GAP;

    setPlace({ left, top, above });
  }, []);

  const show = useCallback(() => {
    position();
    setOpen(true);
  }, [position]);

  const hide = useCallback(() => setOpen(false), []);

  // Bublina je připíchnutá k oknu, ne k dokumentu. Když se pod ní odroluje,
  // musí zmizet, jinak zůstane viset u cizího místa.
  useEffect(() => {
    if (!open) return;
    const onScroll = () => setOpen(false);
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    window.addEventListener('scroll', onScroll, true);
    window.addEventListener('resize', onScroll);
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('scroll', onScroll, true);
      window.removeEventListener('resize', onScroll);
      window.removeEventListener('keydown', onKey);
    };
  }, [open]);

  useLayoutEffect(() => {
    if (open) position();
  }, [open, position]);

  // Pojem, který v glosáři není, se vykreslí jako obyčejný text.
  // Tečkované podtržení slibuje vysvětlení; slib bez obsahu je horší než nic.
  if (!entry) {
    return <>{children ?? id}</>;
  }

  const label = children ?? entry.expansion?.split('—')[0].trim() ?? id;

  return (
    <>
      <button
        ref={anchorRef}
        type="button"
        aria-describedby={open ? tipId : undefined}
        onMouseEnter={show}
        onMouseLeave={hide}
        onFocus={show}
        onBlur={hide}
        onClick={(event) => {
          event.stopPropagation();
          if (open) hide();
          else show();
        }}
        style={{ font: 'inherit', color: 'inherit', letterSpacing: 'inherit' }}
        className={
          'inline cursor-help bg-transparent p-0 text-left underline '
          + 'decoration-dotted decoration-from-font underline-offset-[3px] '
          + `hover:decoration-solid ${className}`
        }
      >
        {label}
      </button>

      {open && place && createPortal(
        <div
          id={tipId}
          role="tooltip"
          style={{
            position: 'fixed',
            left: place.left,
            top: place.top,
            width: WIDTH,
            transform: place.above ? 'translateY(-100%)' : undefined,
            zIndex: 90,
          }}
          className="pointer-events-none rounded-card border border-frame-line bg-frame p-3 shadow-card-hover animate-fade-in"
        >
          {entry.expansion && (
            <p className="font-mono text-[11px] font-medium leading-snug text-frame-text">
              {entry.expansion}
            </p>
          )}
          <p
            className={`text-[12.5px] leading-relaxed text-frame-muted ${entry.expansion ? 'mt-1.5' : ''}`}
          >
            {entry.meaning}
          </p>
          {entry.source && (
            <p className="eyebrow mt-2 text-frame-muted/70">
              {entry.source === 'metodika' ? 'pojem z metodiky' : entry.source}
            </p>
          )}
        </div>,
        document.body,
      )}
    </>
  );
};

export default Term;
