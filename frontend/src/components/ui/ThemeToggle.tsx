/**
 * Přepínač tématu.
 *
 * Tři možnosti, ne dvě. „Podle systému" je skutečný stav a musí jít
 * zvolit — jinak se aplikace večer nepřepne do tmavé jen proto, že si
 * někdo jednou ráno klikl na světlou.
 *
 * Segmentový přepínač místo jednoho cyklujícího tlačítka: u tří stavů
 * je z cyklu poznat, co je zvolené, až po prokliku všech tří.
 */

import React from 'react';
import { Monitor, Moon, Sun } from 'lucide-react';
import { useTheme } from '../../design/useTheme';
import type { ThemeChoice } from '../../design/theme';

interface ThemeToggleProps {
  className?: string;
  /** Na tmavém panelu potřebuje jiné barvy než na listu. */
  tone?: 'frame' | 'sheet';
}

const OPTIONS: { value: ThemeChoice; label: string; Icon: typeof Sun }[] = [
  { value: 'light', label: 'Světlé', Icon: Sun },
  { value: 'dark', label: 'Tmavé', Icon: Moon },
  { value: 'system', label: 'Podle systému', Icon: Monitor },
];

export const ThemeToggle: React.FC<ThemeToggleProps> = ({
  className = '',
  tone = 'frame',
}) => {
  const { choice, setTheme } = useTheme();

  const shell = tone === 'frame'
    ? 'border-frame-line bg-frame-raised'
    : 'border-sheet-rule bg-sheet-alt';

  return (
    <div
      role="radiogroup"
      aria-label="Motiv vzhledu"
      className={`inline-flex items-center gap-0.5 rounded-button border p-0.5 ${shell} ${className}`}
    >
      {OPTIONS.map(({ value, label, Icon }) => {
        const active = choice === value;

        const state = active
          ? tone === 'frame'
            ? 'bg-frame text-frame-text'
            : 'bg-sheet text-sheet-text'
          : tone === 'frame'
            ? 'text-frame-muted hover:text-frame-text'
            : 'text-sheet-muted hover:text-sheet-text';

        return (
          <button
            key={value}
            type="button"
            role="radio"
            aria-checked={active}
            aria-label={label}
            title={label}
            onClick={() => setTheme(value)}
            className={`rounded-[2px] p-1.5 transition-colors ${state}`}
          >
            <Icon size={14} strokeWidth={2} aria-hidden="true" />
          </button>
        );
      })}
    </div>
  );
};

export default ThemeToggle;
