/**
 * DecisionBoard — „co s tímhle" pro dva lidi nad jedním portfoliem.
 *
 *     „Budu já a moje přítelkyně vědět, kdy do čeho investovat, co kdy prodat.
 *      Abychom prostě věděli."
 *
 * Pro každou firmu: pásmo → dvě limitní ceny → co říká Breakout → pokyn pro
 * každého.
 *
 * Tři věci, které tahle obrazovka drží a jinde se rozpadaly:
 *
 * 1. **Pásmo se počítá jednou, pokyn dvakrát.** Pásmo je vlastnost firmy;
 *    kolik toho kdo má a co s tím má dělat je vlastnost účtu. Sečíst oba účty
 *    do jednoho, který nikdo nedrží, byla živá chyba — pozice za 12 % jejího
 *    účtu vyšla jako 6 % součtu a prošla stropem, který měla porazit.
 *
 * 2. **Dva různé pokyny u jedné akcie nejsou spor.** Kdo koupil dřív a levněji,
 *    vybírá zisk dřív. Detail to musí umět ukázat, aniž by to vypadalo
 *    rozbitě — proto jsou oba řádky pod jedním pásmem, ne na dvou kartách.
 *
 * 3. **Ticho je stav, ne prázdno.** Kdo nemá co dělat, dostane řádek, který to
 *    říká. Prázdné místo se čte jako „appka se na to nepodívala", a to je po
 *    třech týdnech bez otevření ten jediný dojem, který nesmí být špatně.
 *
 * Limitní ceny jsou to hlavní. Verdikt je užitečný jen v den, kdy appku někdo
 * otevře; dvě limitky se zadají u brokera jednou a pak už se nemusí koukat.
 *
 * **Seznam vlevo, teze vpravo (přidáno 24. 8. 2026).** Dvanáct plných karet
 * pod sebou porušovalo pravidlo „nic nescrolluje kromě seznamů" — stránka
 * měřila přes čtyři obrazovky. Řádek v seznamu teď nese jen to, co rozlišuje
 * jednu pozici od druhé (pásmo, pokyn pro každého); celý zbytek — dráha,
 * ochranná rezerva, Breakout, poznámky — je teze jedné vybrané firmy vpravo.
 * Scrolluje jen seznam; teze se mění klikem, ne posouváním stránky.
 *
 * Ze stejného důvodu jsou varování o celém portfoliu za kliknutím v okně
 * (`WarningsModal`), ne rozbalená na stránce — šest skupin tam brávalo víc
 * místa než seznam a teze dohromady.
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  Check,
  ChevronRight,
  Minus,
  RefreshCw,
  Search,
  X,
} from 'lucide-react';
import {
  CartesianGrid,
  ComposedChart,
  Label,
  Line,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { apiClient } from '../api/client';
import type { BoardCard, BoardResponse, OhlcvBar, OwnerLine, SafetyLine } from '../types';
import { bandName, bandTone, czk, day, plural, price } from '../lib/format';
import { groupWarnings, stripSeverityEmoji, type WarningGroup } from '../lib/warnings';

const CHART_GRID = 'rgb(var(--rule) / 0.6)';
const CHART_AXIS = 'rgb(var(--text-muted))';

const PriceChartTooltip: React.FC<{
  active?: boolean;
  payload?: { payload: OhlcvBar }[];
  currency?: string | null;
}> = ({ active, payload, currency }) => {
  if (!active || !payload?.length) return null;
  const bar = payload[0].payload;
  return (
    <div className="rounded border border-border-subtle bg-surface-overlay px-2.5 py-1.5 text-[11px] shadow-lg">
      <p className="text-text-muted">{day(bar.date)}</p>
      <p className="font-medium text-text-primary tabular-nums">{price(bar.close, currency)}</p>
    </div>
  );
};

/**
 * Cena v čase, s pásmem promítnutým do grafu — a kde na téhle křivce dnes
 * jsme. Zdroj jsou denní svíčky z `ohlcv_data`, ne živý kurz; proto se
 * chybějící historie ukáže jako věta, ne jako prázdný nebo schovaný graf
 * (stejné pravidlo jako u ochranné rezervy výš).
 */
const PriceChart: React.FC<{
  ticker: string;
  buyBelow?: number | null;
  sellAbove?: number | null;
  currency?: string | null;
}> = ({ ticker, buyBelow, sellAbove, currency }) => {
  const [bars, setBars] = useState<OhlcvBar[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    apiClient
      .getOhlcv(ticker)
      .then((res) => {
        if (!cancelled) setBars(res.data);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [ticker]);

  if (failed) {
    return (
      <p className="text-[11px] text-text-muted">
        Historii ceny nemám — pro {ticker} se ještě nestáhla.
      </p>
    );
  }

  if (!bars) {
    return <div className="h-[160px] animate-pulse rounded bg-surface-active" />;
  }

  if (bars.length < 2) {
    return <p className="text-[11px] text-text-muted">Na křivku je to zatím málo dní.</p>;
  }

  const last = bars[bars.length - 1];

  return (
    <div className="h-[160px] w-full">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={bars} margin={{ top: 10, right: 14, bottom: 0, left: 0 }}>
          <CartesianGrid stroke={CHART_GRID} strokeDasharray="2 4" vertical={false} />
          <XAxis
            dataKey="date"
            tick={{ fill: CHART_AXIS, fontSize: 10, fontFamily: 'IBM Plex Mono' }}
            tickFormatter={(d: string) =>
              new Date(d).toLocaleDateString('cs-CZ', { day: 'numeric', month: 'numeric' })
            }
            tickLine={false}
            axisLine={{ stroke: CHART_GRID }}
            // 180 denních svící při 28 px vyrobilo přes dvacet nalepených
            // popisků — čitelné jako šum, ne jako osa. 64 px drží rozestup,
            // kde se dá skutečně přečíst, na jaký měsíc se dívám.
            minTickGap={64}
            /* Poslední den nese i popisek „teď" — bez místa napravo od
               něj by se text o pravý okraj grafu uřízl. */
            padding={{ left: 4, right: 34 }}
          />
          <YAxis
            domain={['auto', 'auto']}
            tick={{ fill: CHART_AXIS, fontSize: 10, fontFamily: 'IBM Plex Mono' }}
            tickFormatter={(v: number) => price(v, currency)}
            tickLine={false}
            axisLine={false}
            width={58}
          />
          <Tooltip content={<PriceChartTooltip currency={currency} />} cursor={{ stroke: CHART_GRID }} />

          <Line
            type="monotone"
            dataKey="close"
            stroke="rgb(var(--text-primary))"
            strokeWidth={1.5}
            dot={false}
            activeDot={{ r: 3, strokeWidth: 0, fill: 'rgb(var(--text-primary))' }}
            isAnimationActive={false}
          />

          {buyBelow != null && (
            <ReferenceLine
              y={buyBelow}
              ifOverflow="extendDomain"
              stroke="rgb(var(--positive))"
              strokeDasharray="4 3"
              strokeWidth={1.25}
            >
              <Label
                value={`kupovat do ${price(buyBelow, currency)}`}
                position="insideBottomLeft"
                fill="rgb(var(--positive))"
                fontSize={10}
                fontFamily="IBM Plex Mono"
              />
            </ReferenceLine>
          )}
          {sellAbove != null && (
            <ReferenceLine
              y={sellAbove}
              ifOverflow="extendDomain"
              stroke="rgb(var(--warning))"
              strokeDasharray="4 3"
              strokeWidth={1.25}
            >
              {/* Opačný roh než kupovat-do — obě čáry se u „pod svou
                  podlahou" pozic tisknou blízko sebe a stejná strana by se
                  přes sebe přepisovala. */}
              <Label
                value={`odebírat od ${price(sellAbove, currency)}`}
                position="insideTopRight"
                fill="rgb(var(--warning))"
                fontSize={10}
                fontFamily="IBM Plex Mono"
              />
            </ReferenceLine>
          )}

          <ReferenceDot
            x={last.date}
            y={last.close}
            r={3.5}
            fill="rgb(var(--text-primary))"
            stroke="rgb(var(--surface-raised))"
            strokeWidth={1.5}
            ifOverflow="extendDomain"
          >
            {/* Poslední den je zároveň pravý okraj osy — popisek vpravo od
                bodu by vyjel z grafu ven a vlevo se plete do dat. Nahoře je
                jediné volné místo, co zbývá. */}
            <Label
              value={`teď ${price(last.close, currency)}`}
              position="top"
              fill="rgb(var(--text-primary))"
              fontSize={10}
              fontFamily="IBM Plex Mono"
            />
          </ReferenceDot>
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
};

interface DecisionBoardProps {
  /** Bump to force a refetch (např. po zapsaném obchodu). */
  refreshKey?: number;
}

/*
 * Pokyn nese slovo, ne barvu jako jediný nosič. Barva se nedá přečíst
 * nahlas a část lidí ji nerozliší; slovo funguje vždycky.
 */
const INSTRUCTION_TONE: Record<string, string> = {
  KOUPIT: 'bg-positive-bg text-positive border-positive-border',
  PŘIKOUPIT: 'bg-positive-bg text-positive border-positive-border',
  ODEBRAT: 'bg-warning-bg text-warning border-warning-border',
  PRODAT: 'bg-negative-bg text-negative border-negative-border',
  'PRODAT VŠE': 'bg-negative-bg text-negative border-negative-border',
  DRŽ: 'bg-surface-active text-text-secondary border-border-subtle',
  NEMÁ: 'bg-transparent text-text-muted border-transparent',
  /*
   * Rozpor a prázdné místo nesou varovný tón, ne klidný. Obojí je otázka
   * na tebe, ne stav, ve kterém se dá nechat být.
   */
  'ROZHODNI TY': 'bg-warning-bg text-warning border-warning-border',
  'DRŽÍŠ — NEVÍM': 'bg-warning-bg text-warning border-warning-border',
};

const STANCE: Record<string, { icon: React.ReactNode; label: string; tone: string }> = {
  SOUHLASI: {
    icon: <Check size={13} className="text-positive shrink-0" />,
    label: 'souhlasí s Gomesem',
    tone: 'text-positive',
  },
  NESOUHLASI: {
    icon: <X size={13} className="text-warning shrink-0" />,
    label: 'nesouhlasí s Gomesem',
    tone: 'text-warning',
  },
  MLCI: {
    icon: <Minus size={13} className="text-text-muted shrink-0" />,
    label: 'k tomu nemá stanovisko',
    tone: 'text-text-muted',
  },
};

/**
 * Kde cena leží vůči tomu, co si firma zaslouží.
 *
 * Osa je R/R skóre 0–10, ne poloha v cenovém rozpětí — to jsou dvě různé věci
 * a prohlížeč dlouho ukazoval tu druhou. Zasloužená úroveň (`10 − válce`) je
 * na dráze vyznačená zvlášť, protože pásmo je právě rozdíl mezi těmi dvěma
 * značkami: stejná cena u lepší firmy je jiné pásmo.
 */
const BandScale: React.FC<{ score: number | null; deserved: number | null; tone: string }> = ({
  score,
  deserved,
  tone,
}) => {
  if (score === null) return null;
  const clamp = (v: number) => Math.max(0, Math.min(100, v * 10));
  // The label reads at a position; it has to sit at that position. `flex
  // justify-between` used to put "zaslouží X" at the row's visual center no
  // matter what X was — for a deserved score of 7 the word sat at 50 % while
  // its own tick, drawn correctly below, sat at 70 %. Clamped narrower than
  // the tick itself only so the text doesn't clip under "drahé"/"levné".
  const labelLeft = deserved !== null ? Math.min(90, Math.max(10, clamp(deserved))) : null;

  return (
    <div className="mt-1.5">
      <div className="relative h-1.5 rounded-full bg-surface-active overflow-hidden">
        {deserved !== null && (
          <div
            className="absolute top-0 h-full w-px bg-text-muted"
            style={{ left: `${clamp(deserved)}%` }}
            aria-hidden="true"
          />
        )}
        <div
          className={`absolute top-0 h-full w-1 rounded-full ${tone}`}
          style={{ left: `calc(${clamp(score)}% - 2px)` }}
        />
      </div>
      <div className="relative h-3 text-[10px] text-text-muted mt-0.5 tabular-nums">
        <span className="absolute left-0">drahé</span>
        {labelLeft !== null && (
          <span
            className="absolute -translate-x-1/2 whitespace-nowrap"
            style={{ left: `${labelLeft}%` }}
          >
            zaslouží {deserved!.toLocaleString('cs-CZ')}
          </span>
        )}
        <span className="absolute right-0">levné</span>
      </div>
    </div>
  );
};


/**
 * Ochranná rezerva — jediné místo na kartě, které měří dolů.
 *
 * Všechno ostatní počítá vzdálenost ke stropu: pásmo, R/R skóre, cíl
 * Breakoutu. Tohle se ptá opačně — co drží cenu zdola, když se teze rozpadne.
 *
 * Chybějící podlaha se ukáže jako chybějící, ne jako nula. „Nespočítám" a
 * „není kam padat" jsou dvě různé věty a jen jedna z nich je uklidňující.
 */
const LAYER_CS: Record<string, string> = {
  TANGIBLE_BOOK: 'z hmotných aktiv',
  NET_CASH: 'jen z čisté hotovosti',
  NONE: '',
};

const Safety: React.FC<{ line: SafetyLine; currency?: string | null }> = ({
  line,
  currency,
}) => {
  if (line.floor == null || line.downside_pct == null) {
    return (
      <p className="text-[11px] text-text-muted leading-snug">
        Ochrannou rezervu nespočítám — neznamená to, že tam žádná není.
      </p>
    );
  }

  const tone = line.below_floor
    ? 'text-positive'
    : line.downside_pct < 15
      ? 'text-warning'
      : 'text-text-secondary';

  return (
    <div className="space-y-0.5">
      <p className={`text-[11px] font-medium ${tone}`}>
        {line.below_floor
          ? 'Pod svou podlahou'
          : `Dolů ${Math.round(line.downside_pct)} % k podlaze`}{' '}
        <span className="tabular-nums">{price(line.floor, currency)}</span>{' '}
        <span className="text-text-muted font-normal">{LAYER_CS[line.layer]}</span>
      </p>
      {line.asymmetry != null && line.upside_pct != null && (
        <p className="text-[11px] text-text-muted tabular-nums">
          nahoru {Math.round(line.upside_pct)} % · poměr{' '}
          {line.asymmetry.toLocaleString('cs-CZ', { maximumFractionDigits: 1 })}
        </p>
      )}
    </div>
  );
};

const OwnerRow: React.FC<{ line: OwnerLine }> = ({ line }) => {
  const tone = INSTRUCTION_TONE[line.instruction_cs] ?? INSTRUCTION_TONE.DRŽ;
  const quiet = line.instruction_cs === 'NEMÁ';

  return (
    <div
      className={`flex items-start gap-2.5 py-1.5 ${quiet ? 'opacity-55' : ''}`}
    >
      <span className="text-xs text-text-secondary w-16 shrink-0 pt-0.5 truncate">
        {line.owner}
      </span>
      <span
        className={`text-[10px] font-semibold px-1.5 py-0.5 rounded border shrink-0 ${tone}`}
      >
        {line.instruction_cs}
      </span>
      <div className="min-w-0 flex-1">
        {/* Nejdřív to, co se zadává brokerovi. Důvod až pod tím — kdo appce
            věří, nemusí ho číst; kdo ne, potřebuje ho vidět celý. */}
        {line.quantity != null && line.quantity > 0 && (
          <p className="text-xs text-text-primary tabular-nums">
            {line.quantity.toLocaleString('cs-CZ')} ks
            {line.limit_price != null && (
              <> limitem <strong>{price(line.limit_price, line.limit_currency)}</strong></>
            )}
            {line.estimated_czk != null && line.estimated_czk > 0 && (
              <span className="text-text-muted"> ≈ {czk(line.estimated_czk)}</span>
            )}
          </p>
        )}
        <p className="text-[11px] text-text-muted leading-snug">{line.detail_cs}</p>
        {line.valid_until && (
          <p className="text-[10px] text-text-muted mt-0.5">
            platí do {day(line.valid_until)}
          </p>
        )}
      </div>
    </div>
  );
};

/** Jeden řádek v seznamu vlevo — jen to, čím se pozice liší od ostatních. */
const ListRow: React.FC<{ card: BoardCard; active: boolean; onSelect: () => void }> = ({
  card,
  active,
  onSelect,
}) => {
  const tone = bandTone(card.band);

  return (
    <button
      type="button"
      onClick={onSelect}
      aria-current={active}
      className={`flex w-full items-center gap-2 px-2.5 py-2 text-left transition-colors ${
        active ? 'bg-accent-bg' : 'hover:bg-surface-hover'
      }`}
    >
      <span
        className={`inline-flex shrink-0 items-center justify-center whitespace-nowrap rounded border px-1 py-0.5 text-[9px] font-semibold min-w-[84px] text-center ${tone.pill}`}
      >
        {bandName(card.band)}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[13px] font-medium text-text-primary">
          {card.ticker}
        </span>
        {card.company_name && (
          <span className="block truncate text-[10.5px] text-text-muted">
            {card.company_name}
          </span>
        )}
      </span>
      {/* Iniciála pro každý účet, barva podle jeho pokynu. Dva různé pokyny
          u jedné akcie nejsou chyba (pravidlo č. 2 nahoře) — seznam to musí
          ukázat na první pohled, ne až v tezi. */}
      <span className="flex shrink-0 gap-1">
        {card.owners.map((o) => (
          <span
            key={o.portfolio_id}
            title={`${o.owner}: ${o.instruction_cs}`}
            className={`flex h-4 w-4 items-center justify-center rounded border text-[8px] font-bold ${
              INSTRUCTION_TONE[o.instruction_cs] ?? INSTRUCTION_TONE.DRŽ
            } ${o.instruction_cs === 'NEMÁ' ? 'opacity-40' : ''}`}
          >
            {o.owner.slice(0, 1).toUpperCase()}
          </span>
        ))}
      </span>
    </button>
  );
};

/** Teze jedné firmy — celý zbytek toho, co karta ví, pro vybranou pozici. */
const CardDetail: React.FC<{ card: BoardCard }> = ({ card }) => {
  const tone = bandTone(card.band);
  const stance = card.breakout ? STANCE[card.breakout.stance] ?? STANCE.MLCI : null;

  return (
    <article className="rounded border border-border-subtle bg-surface-raised p-3">
      <header className="flex items-baseline justify-between gap-2">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-text-primary">
            {card.ticker}
            {card.company_name && (
              <span className="text-text-muted font-normal"> · {card.company_name}</span>
            )}
          </h3>
        </div>
        <span
          className={`text-[10px] font-semibold px-1.5 py-0.5 rounded border shrink-0 ${tone.pill}`}
        >
          {bandName(card.band)}
        </span>
      </header>

      {/* Pásmo: značka na dráze plus věta, proč tam je. */}
      <BandScale score={card.rr_score} deserved={card.deserved} tone={tone.marker} />
      <p className="text-[11px] text-text-secondary leading-snug mt-1.5">
        {card.band_reason_cs}
      </p>

      {card.quality_expired && (
        <p className="text-[11px] text-warning mt-1.5 flex items-start gap-1.5">
          <AlertTriangle size={12} className="shrink-0 mt-0.5" />
          Potvrzení kvality firmy vypršelo — na prodej to platí dál, na nákup ne.
        </p>
      )}

      {/* Dvě limitky. Kvůli nim se sem chodí. Počítají se z linií, ne z dnešní
          ceny, takže zastaralý kurz je nezkazí. */}
      {(card.buy_below != null || card.sell_above != null) && (
        <dl className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs">
          {card.buy_below != null && (
            <div className="flex gap-1.5">
              <dt className="text-text-muted">kupovat do</dt>
              <dd className="text-text-primary tabular-nums font-medium">
                {price(card.buy_below, card.line_currency)}
              </dd>
            </div>
          )}
          {card.sell_above != null && (
            <div className="flex gap-1.5">
              <dt className="text-text-muted">odebírat od</dt>
              <dd className="text-text-primary tabular-nums font-medium">
                {price(card.sell_above, card.line_currency)}
              </dd>
            </div>
          )}
        </dl>
      )}

      {/* Cena v čase, s limitkami promítnutými do křivky — a kde na ní dnes
          jsme. Tytéž dvě hodnoty jako v `<dl>` výš, jen jako obrázek místo
          čísla; kdo si je pod textem nedovede představit v pohybu, tady je
          uvidí. */}
      <div className="mt-2 pt-2 border-t border-border-subtle">
        {/* key=ticker: nová firma je nová instance, ne přepočítaný stav
            té staré — jinak by graf jednoho tickeru krátce probleskl
            s daty ještě od předchozího. */}
        <PriceChart
          key={card.ticker}
          ticker={card.ticker}
          buyBelow={card.buy_below}
          sellAbove={card.sell_above}
          currency={card.line_currency}
        />
      </div>

      {/* Kolik se dá ztratit. Jediné čtení, které měří dolů — a schválně
          hned pod limitkami, protože „kupovat do X" bez „a dolů je Y" je
          jen polovina rozhodnutí. */}
      {card.safety && (
        <div className="mt-2 pt-2 border-t border-border-subtle">
          <Safety line={card.safety} currency={card.line_currency} />
        </div>
      )}

      {/* Druhý zdroj. Nikdy nákup nepovolí — smí ho jen zastavit. */}
      {card.breakout && stance && (
        <div className="mt-2 pt-2 border-t border-border-subtle">
          <div className="flex items-start gap-1.5">
            {stance.icon}
            <div className="min-w-0">
              <p className={`text-[11px] font-medium ${stance.tone}`}>
                Breakout {stance.label}
                {card.breakout.analyst && (
                  <span className="text-text-muted font-normal">
                    {' '}· napsal {card.breakout.analyst}
                  </span>
                )}
              </p>
              <p className="text-[11px] text-text-muted leading-snug">
                {card.breakout.summary_cs}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Co appka o téhle firmě ví, i když z toho nevzejde pokyn. Osm
          z dvanácti pozic nemá ocenění a tohle je jediné, co se o nich dá
          říct — dřív to viselo ve zdi nad kartami, kde každý řádek opakoval
          to, co jeho vlastní karta stejně říkala. */}
      {card.notes_cs.length > 0 && (
        <ul className="mt-2 pt-2 border-t border-border-subtle space-y-1">
          {card.notes_cs.map((note, i) => (
            <li
              key={i}
              className="text-[11px] text-text-muted leading-snug flex gap-1.5"
            >
              <span aria-hidden="true" className="text-text-muted/60">·</span>
              <span className="min-w-0">{stripSeverityEmoji(note)}</span>
            </li>
          ))}
        </ul>
      )}

      {/* Kdo co má udělat. Oba vždycky, i když jeden z nich nic. */}
      <div className="mt-2 pt-2 border-t border-border-subtle divide-y divide-border-subtle">
        {card.owners.map((line) => (
          <OwnerRow key={line.portfolio_id} line={line} />
        ))}
      </div>
    </article>
  );
};

/**
 * Plné znění varování o celém portfoliu, na kliknutí z lišty pod ním.
 *
 * Rozbalené rovnou pod hlavičkou braly šest skupin i přes 300 px — u toho,
 * co je pro portfolio pravda pořád, ne jen pro vybranou pozici, to bylo víc
 * místa, než pro seznam a tezi dohromady. Za oknem to zůstává čitelné celé,
 * jen to nezabírá místo, dokud se o to nikdo nezajímá.
 */
const WarningsModal: React.FC<{ warnings: WarningGroup[]; onClose: () => void }> = ({
  warnings,
  onClose,
}) => (
  <div
    className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
    onClick={onClose}
  >
    <div
      className="flex max-h-[80vh] w-full max-w-xl flex-col rounded-card border border-border bg-surface-overlay shadow-xl"
      onClick={(e) => e.stopPropagation()}
    >
      <header className="flex shrink-0 items-center justify-between gap-2 border-b border-border-subtle px-4 py-3">
        <h3 className="text-sm font-semibold text-text-primary">
          Na co si dát pozor ({warnings.length})
        </h3>
        <button
          onClick={onClose}
          className="rounded p-1 text-text-muted transition-colors hover:text-text-primary"
          aria-label="Zavřít"
        >
          <X size={16} />
        </button>
      </header>
      <div className="min-h-0 overflow-y-auto divide-y divide-border-subtle">
        {warnings.map((group, index) => (
          <div key={`${group.kind}-${index}`} className="px-4 py-3">
            <div className="flex items-baseline gap-2">
              <AlertTriangle
                size={12}
                className="shrink-0 translate-y-0.5 text-warning"
                aria-hidden="true"
              />
              <span className="text-[11.5px] font-medium text-warning">
                {group.kind === 'JINE'
                  ? stripSeverityEmoji(group.label)
                  : `${group.count} ${plural(group.count, 'pozice', 'pozice', 'pozic')} — ${group.label}`}
              </span>
            </div>
            {group.consequence && (
              <p className="mt-0.5 pl-5 text-[11px] leading-relaxed text-text-secondary">
                {group.consequence}
              </p>
            )}
            {group.tickers.length > 0 && group.tickers.length <= 6 && (
              <p className="mt-0.5 pl-5 text-[10.5px] text-text-muted">
                {group.tickers.join(' · ')}
              </p>
            )}
          </div>
        ))}
      </div>
    </div>
  </div>
);

export const DecisionBoard: React.FC<DecisionBoardProps> = ({ refreshKey = 0 }) => {
  const [data, setData] = useState<BoardResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState('');
  const [selected, setSelected] = useState<string | null>(null);
  const [warningsOpen, setWarningsOpen] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await apiClient.getBoard());
    } catch (e) {
      // Chyba se ukáže jako chyba. Prázdná tabule by se četla jako
      // „není co řešit", což je přesně ta nejhorší možná lež.
      setError(e instanceof Error ? e.message : 'Tabuli se nepodařilo načíst');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  // Výběr přežije refetch, dokud pozice v tabuli zůstává; jinak spadne na
  // první kartu, aby detail vpravo nikdy nezůstal prázdný zbytečně.
  useEffect(() => {
    if (!data) return;
    setSelected((prev) =>
      prev && data.cards.some((c) => c.ticker === prev) ? prev : (data.cards[0]?.ticker ?? null)
    );
  }, [data]);

  const filtered = useMemo(() => {
    if (!data) return [];
    const q = filter.trim().toLowerCase();
    if (!q) return data.cards;
    return data.cards.filter(
      (c) => c.ticker.toLowerCase().includes(q) || c.company_name?.toLowerCase().includes(q)
    );
  }, [data, filter]);

  const selectedCard = data?.cards.find((c) => c.ticker === selected) ?? null;

  if (loading && !data) {
    return (
      <div className="rounded border border-border-subtle bg-surface-raised p-6 text-center">
        <RefreshCw size={16} className="animate-spin mx-auto text-text-muted" />
        <p className="text-xs text-text-muted mt-2">Počítám pásma a pokyny…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded border border-negative-border bg-negative-bg p-4">
        <p className="text-xs text-negative flex items-start gap-2">
          <AlertTriangle size={14} className="shrink-0 mt-0.5" />
          {error}
        </p>
        <button
          onClick={() => void load()}
          className="text-xs text-text-secondary underline mt-2"
        >
          Zkusit znovu
        </button>
      </div>
    );
  }

  if (!data || data.cards.length === 0) {
    return (
      <div className="rounded border border-border-subtle bg-surface-raised p-6 text-center">
        <p className="text-sm text-text-secondary">Žádné pozice k zobrazení.</p>
      </div>
    );
  }

  const warnings = groupWarnings(data.warnings ?? []);

  return (
    <section className="flex min-h-0 flex-1 flex-col gap-3">
      <header className="shrink-0 flex items-baseline justify-between">
        <h2 className="text-sm font-semibold text-text-primary">Co s tímhle</h2>
        <button
          onClick={() => void load()}
          className="text-[11px] text-text-muted hover:text-text-secondary flex items-center gap-1"
        >
          <RefreshCw size={11} className={loading ? 'animate-spin' : ''} />
          Přepočítat
        </button>
      </header>

      {/* Varování o celém portfoliu patří NAD seznam i tezi: mění to, jak se
          má číst každá pozice, ne jen ta vybraná. Rozbalené na stránce ale
          brávaly víc místa než seznam a teze dohromady — proto je tu jen
          lišta s tím nejdůležitějším a plné znění je za kliknutím v okně. */}
      {warnings.length > 0 && (
        <button
          type="button"
          onClick={() => setWarningsOpen(true)}
          className="flex shrink-0 items-center gap-2 rounded border border-warning-border bg-warning-bg px-3 py-1.5 text-left transition-colors hover:bg-warning-bg/70"
        >
          <AlertTriangle size={13} className="shrink-0 text-warning" aria-hidden="true" />
          <span className="text-[11.5px] font-medium text-warning shrink-0">
            {warnings.length} {plural(warnings.length, 'upozornění', 'upozornění', 'upozornění')} k portfoliu
          </span>
          <span className="min-w-0 truncate text-[10.5px] text-text-muted">
            {stripSeverityEmoji(warnings[0].label)}
          </span>
          <ChevronRight size={13} className="ml-auto shrink-0 text-text-muted" aria-hidden="true" />
        </button>
      )}

      {warningsOpen && (
        <WarningsModal warnings={warnings} onClose={() => setWarningsOpen(false)} />
      )}

      {/* Seznam vlevo scrolluje sám v sobě; teze vpravo se mění klikem.
          Tohle je to jediné místo na stránce, kde se posouvá — přesně podle
          pravidla „nic nescrolluje kromě seznamů". */}
      <div className="grid min-h-0 flex-1 grid-cols-1 gap-3 xl:grid-cols-[280px_minmax(0,1fr)]">
        <div className="flex min-h-0 flex-col rounded border border-border-subtle bg-surface-raised">
          <div className="shrink-0 border-b border-border-subtle p-2">
            <div className="relative">
              <Search
                size={13}
                className="pointer-events-none absolute left-2 top-1/2 -translate-y-1/2 text-text-muted"
              />
              <input
                type="text"
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                placeholder="Hledat tiket nebo firmu…"
                className="w-full rounded border border-border-subtle bg-surface py-1.5 pl-7 pr-2 text-xs text-text-primary placeholder-text-muted focus:outline-none focus:border-accent"
              />
            </div>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto divide-y divide-border-subtle">
            {filtered.length === 0 ? (
              <p className="p-3 text-xs text-text-muted">Nic neodpovídá hledání.</p>
            ) : (
              filtered.map((card) => (
                <ListRow
                  key={card.ticker}
                  card={card}
                  active={card.ticker === selected}
                  onSelect={() => setSelected(card.ticker)}
                />
              ))
            )}
          </div>
        </div>

        <div className="min-h-0 overflow-y-auto pr-0.5">
          {selectedCard && <CardDetail card={selectedCard} />}
        </div>
      </div>
    </section>
  );
};

export default DecisionBoard;
