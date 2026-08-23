/**
 * Platby — pět knih na jedné obrazovce.
 *
 * Předtím pod sebou stálo pět bloků, každý s vlastním nadpisem, vlastní
 * kartou souhrnu a vlastním prázdným stavem s kolečkem 80 × 80 px. Dohromady
 * 1 915 px, tedy skoro tři obrazovky, a číslo, které člověk hledá — kolik
 * měsíčně odchází — nebylo vidět ani jednou. Bylo rozsypané do pěti karet
 * „Celkem za měsíc", každá na jiné obrazovce.
 *
 * Teď je nahoře řádek souhrnu, pod ním odrážky (jedna na knihu, každá se
 * svou měsíční částkou) a pod nimi tabulka té knihy, na kterou se člověk
 * přepnul. Všech pět částek je vidět naráz, aniž by se scrollovalo, a
 * podrobnosti se rozbalí kliknutím.
 *
 * Žádný údaj nezmizel — jen se každý říká právě jednou. „Měsíční splátka"
 * a čtyři „Celkem za měsíc" ze starých karet jsou dnes částky na odrážkách,
 * zbytek stojí v souhrnu.
 *
 * Data i formuláře zůstávají v InvestmentTerminal. Tahle komponenta jen
 * kreslí — nedrží stav, nezapisuje do localStorage, a proto nemůže o nic
 * přijít.
 */

import React, { useMemo, useState } from 'react';
import { Edit3, Plus } from 'lucide-react';

export interface PaymentRecord {
  id: number;
  name: string;
  amount: string;
  date: string;
  monthlyPayment: string;
  creditor: string;
  accountNumber: string;
  variableSymbol: string;
  note: string;
}

interface LedgerSpec {
  id: string;
  /** Jméno knihy na odrážce. */
  label: string;
  items: PaymentRecord[];
  /** Splácení má navíc částku, zbytek a datum první splátky. */
  kind: 'debt' | 'payment';
  /** Věta do prázdného stavu — co se sem zapisuje. */
  emptyHint: string;
  onAdd: () => void;
  onEdit: (item: PaymentRecord) => void;
}

interface PaymentsPageProps {
  debts: PaymentRecord[];
  sharedPayments: PaymentRecord[];
  misaPayments: PaymentRecord[];
  savings: PaymentRecord[];
  tomPayments: PaymentRecord[];
  formatCurrency: (value: number, currency?: string) => string;
  onAdd: (ledger: string) => void;
  onEdit: (ledger: string, item: PaymentRecord) => void;
}

/** Číslo z textového pole. Prázdné i nesmyslné je nula, nikdy NaN. */
function num(value: string | null | undefined): number {
  const n = parseFloat(value ?? '');
  return Number.isFinite(n) ? n : 0;
}

/**
 * Kolik měsíců uplynulo od první splátky včetně.
 *
 * Nevyplněné ani nesmyslné datum dá nulu. Bez téhle pojistky vyrobil
 * `new Date('')` hodnotu Invalid Date, ta prošla aritmetikou jako NaN a
 * v tabulce stálo „NaN Kč" — přesně ten druh vady, kdy chybějící údaj
 * vypadá jako údaj.
 */
function monthsSince(date: string): number {
  const start = new Date(date);
  if (Number.isNaN(start.getTime())) return 0;
  const now = new Date();
  const months =
    (now.getFullYear() - start.getFullYear()) * 12 + (now.getMonth() - start.getMonth()) + 1;
  return Math.max(0, months);
}

/** Kolik už je na závazku zaplaceno. */
function paidSoFar(item: PaymentRecord): number {
  return monthsSince(item.date) * num(item.monthlyPayment);
}

/** Kolik na závazku zbývá. Nikdy pod nulu — přeplatek není dluh. */
function remainingOn(item: PaymentRecord): number {
  return Math.max(0, num(item.amount) - paidSoFar(item));
}

function monthlyTotal(items: PaymentRecord[]): number {
  return items.reduce((sum, item) => sum + num(item.monthlyPayment), 0);
}

export const PaymentsPage: React.FC<PaymentsPageProps> = ({
  debts,
  sharedPayments,
  misaPayments,
  savings,
  tomPayments,
  formatCurrency,
  onAdd,
  onEdit,
}) => {
  const ledgers: LedgerSpec[] = useMemo(
    () => [
      {
        id: 'debts',
        label: 'Společné splácení',
        items: debts,
        kind: 'debt',
        emptyHint: 'Hypotéka, leasing, půjčka — cokoli, co se splácí po měsících.',
        onAdd: () => onAdd('debts'),
        onEdit: (item) => onEdit('debts', item),
      },
      {
        id: 'shared',
        label: 'Společné platby',
        items: sharedPayments,
        kind: 'payment',
        emptyHint: 'Pravidelné platby, které jdou napůl.',
        onAdd: () => onAdd('shared'),
        onEdit: (item) => onEdit('shared', item),
      },
      {
        id: 'misa',
        label: 'Platby Míša',
        items: misaPayments,
        kind: 'payment',
        emptyHint: 'Míšiny vlastní pravidelné platby.',
        onAdd: () => onAdd('misa'),
        onEdit: (item) => onEdit('misa', item),
      },
      {
        id: 'savings',
        label: 'Šetření Míša',
        items: savings,
        kind: 'payment',
        emptyHint: 'Kam si Míša měsíčně odkládá.',
        onAdd: () => onAdd('savings'),
        onEdit: (item) => onEdit('savings', item),
      },
      {
        id: 'tom',
        label: 'Platby Tom',
        items: tomPayments,
        kind: 'payment',
        emptyHint: 'Tomovy vlastní pravidelné platby.',
        onAdd: () => onAdd('tom'),
        onEdit: (item) => onEdit('tom', item),
      },
    ],
    [debts, sharedPayments, misaPayments, savings, tomPayments, onAdd, onEdit],
  );

  const [activeId, setActiveId] = useState(ledgers[0].id);
  const active = ledgers.find((l) => l.id === activeId) ?? ledgers[0];

  /* Souhrn. Měsíční částky jednotlivých knih tu nejsou — ty stojí na
     odrážkách. Opakovat je i tady by byl přesně ten šum, kvůli kterému
     se stránka předělávala. */
  const summary = useMemo(() => {
    const everyMonth = ledgers.reduce((sum, l) => sum + monthlyTotal(l.items), 0);
    return {
      everyMonth,
      remaining: debts.reduce((sum, d) => sum + remainingOn(d), 0),
      total: debts.reduce((sum, d) => sum + num(d.amount), 0),
      paid: debts.reduce((sum, d) => sum + paidSoFar(d), 0),
      perPerson: monthlyTotal(sharedPayments) / 2,
    };
  }, [ledgers, debts, sharedPayments]);

  /* Sloupec Informace se kreslí, jen když v něm něco je. Sloupec pomlček
     zabírá místo a nic neříká. */
  const showNote = active.items.some((item) => Boolean(item.note));
  const showCreditor = active.kind === 'debt' && active.items.some((item) => Boolean(item.creditor));

  return (
    <div className="flex h-full min-h-0 flex-col gap-3">

      {/* ------------------------------------------------------------------
          SOUHRN — pět čísel, která platí napříč knihami.
      ------------------------------------------------------------------ */}
      <div className="grid shrink-0 grid-cols-5 gap-px overflow-hidden rounded-card border border-border bg-border">
        <SummaryCell
          label="Měsíčně celkem"
          value={formatCurrency(summary.everyMonth)}
          hint="Součet všech pěti knih — kolik každý měsíc odejde z účtů."
          strong
        />
        <SummaryCell
          label="Zbývá uhradit"
          value={formatCurrency(summary.remaining)}
          hint="Ze společného splácení, po odečtení dosud zaplacených splátek."
        />
        <SummaryCell label="Celkový dluh" value={formatCurrency(summary.total)} hint="Původní výše všech závazků." />
        <SummaryCell label="Splaceno" value={formatCurrency(summary.paid)} hint="Splátky × měsíce od první splátky." />
        <SummaryCell
          label="Na jednoho"
          value={formatCurrency(summary.perPerson)}
          hint="Polovina společných plateb."
        />
      </div>

      {/* ------------------------------------------------------------------
          ODRÁŽKY — jedna na knihu, s vlastní měsíční částkou.

          Částka na odrážce je celý důvod, proč tenhle pruh existuje: bez
          ní by se člověk musel na každou knihu přepnout, aby zjistil,
          kolik z ní odchází.
      ------------------------------------------------------------------ */}
      <div className="flex shrink-0 flex-wrap items-stretch gap-2" role="tablist" aria-label="Knihy plateb">
        {ledgers.map((ledger) => {
          const on = ledger.id === active.id;
          const monthly = monthlyTotal(ledger.items);
          return (
            <button
              key={ledger.id}
              role="tab"
              aria-selected={on}
              onClick={() => setActiveId(ledger.id)}
              className={`flex min-w-[160px] flex-col gap-0.5 rounded-card border px-3 py-2 text-left transition-colors ${
                on
                  ? 'border-accent-border bg-accent-bg'
                  : 'border-border bg-surface-raised hover:bg-surface-hover'
              }`}
            >
              <span className="flex items-center gap-1.5">
                <span
                  className={`h-[6px] w-[6px] shrink-0 rounded-full ${on ? 'bg-accent' : 'bg-text-muted'}`}
                  aria-hidden="true"
                />
                <span
                  className={`text-[12px] font-medium ${on ? 'text-accent' : 'text-text-secondary'}`}
                >
                  {ledger.label}
                </span>
              </span>
              <span className="flex items-baseline gap-1.5 pl-[13px]">
                <span className="font-mono text-[14px] tabular-nums text-text-primary">
                  {formatCurrency(monthly)}
                </span>
                <span className="text-[10px] text-text-muted">
                  {ledger.items.length === 0
                    ? 'prázdné'
                    : `${ledger.items.length} ${polozek(ledger.items.length)}`}
                </span>
              </span>
            </button>
          );
        })}
      </div>

      {/* ------------------------------------------------------------------
          KNIHA — tabulka té odrážky, na které člověk stojí.
      ------------------------------------------------------------------ */}
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-card border border-border bg-surface-raised">
        <div className="flex shrink-0 items-center justify-between border-b border-border-subtle px-3 py-2">
          <h2 className="text-[13px] font-semibold text-text-primary">{active.label}</h2>
          <button
            onClick={active.onAdd}
            className="flex items-center gap-1.5 rounded-button border border-border px-2.5 py-1 text-[12px] text-text-secondary transition-colors hover:bg-surface-hover hover:text-text-primary"
          >
            <Plus className="h-3.5 w-3.5" />
            Přidat
          </button>
        </div>

        {active.items.length === 0 ? (
          /* Prázdný stav na jednu řádku. Kolečko 80 × 80 px se zelenou
             fajfkou tu dřív slavilo, že se nic neeviduje — a zabíralo
             výšku pěti záznamů. */
          <div className="flex flex-1 flex-col items-center justify-center gap-2 px-4 py-8 text-center">
            <p className="text-[13px] text-text-secondary">Zatím tu nic není.</p>
            <p className="max-w-sm text-[12px] text-text-muted">{active.emptyHint}</p>
          </div>
        ) : (
          <div className="min-h-0 flex-1 overflow-y-auto">
            <table className="w-full">
              <thead className="sticky top-0 z-10 bg-surface-raised">
                <tr className="border-b border-border">
                  <Th>Název</Th>
                  {active.kind === 'debt' && <Th align="right">Částka</Th>}
                  {active.kind === 'debt' && <Th align="right">Zbývá</Th>}
                  {active.kind === 'debt' && <Th align="right">Splaceno</Th>}
                  <Th align="right">Splátka</Th>
                  {active.kind === 'debt' && <Th>1. splátka</Th>}
                  {showCreditor && <Th>Komu</Th>}
                  <Th>Číslo účtu</Th>
                  <Th>VS</Th>
                  {showNote && <Th>Informace</Th>}
                  <Th align="right"> </Th>
                </tr>
              </thead>
              <tbody>
                {active.items.map((item) => (
                  <tr
                    key={item.id}
                    className="group border-b border-border-subtle transition-colors hover:bg-surface-hover"
                  >
                    <Td>
                      <span className="text-[13px] text-text-primary">{item.name || '—'}</span>
                    </Td>

                    {active.kind === 'debt' && (
                      <Td align="right" mono>
                        {item.amount ? formatCurrency(num(item.amount)) : '—'}
                      </Td>
                    )}
                    {active.kind === 'debt' && (
                      <Td align="right" mono>
                        {item.amount ? formatCurrency(remainingOn(item)) : '—'}
                      </Td>
                    )}
                    {active.kind === 'debt' && (
                      <Td align="right" mono muted>
                        {item.date ? formatCurrency(paidSoFar(item)) : '—'}
                      </Td>
                    )}

                    <Td align="right" mono>
                      {item.monthlyPayment ? formatCurrency(num(item.monthlyPayment)) : '—'}
                    </Td>

                    {active.kind === 'debt' && (
                      <Td muted>
                        {item.date && !Number.isNaN(new Date(item.date).getTime())
                          ? new Date(item.date).toLocaleDateString('cs-CZ')
                          : '—'}
                      </Td>
                    )}

                    {showCreditor && <Td muted>{item.creditor || '—'}</Td>}

                    <Td mono muted>{item.accountNumber || '—'}</Td>
                    <Td mono muted>{item.variableSymbol || '—'}</Td>

                    {showNote && (
                      <Td muted>
                        <span className="block max-w-[220px] truncate" title={item.note}>
                          {item.note || '—'}
                        </span>
                      </Td>
                    )}

                    <Td align="right">
                      <button
                        onClick={() => active.onEdit(item)}
                        className="rounded p-1 text-text-muted opacity-0 transition-opacity hover:text-accent focus:opacity-100 group-hover:opacity-100"
                        title="Upravit"
                      >
                        <Edit3 className="h-3.5 w-3.5" />
                      </button>
                    </Td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

/* -------------------------------------------------------------------------
   Drobné stavební prvky. Odděleny proto, aby se rozestupy daly změnit na
   jednom místě — nesourodé odsazení bylo půlka toho zmatku.
------------------------------------------------------------------------- */

const SummaryCell: React.FC<{
  label: string;
  value: string;
  hint: string;
  strong?: boolean;
}> = ({ label, value, hint, strong }) => (
  <div className="bg-surface-raised px-3 py-2" title={hint}>
    <div className="eyebrow text-text-muted">{label}</div>
    <div
      className={`mt-0.5 font-mono tabular-nums ${
        strong ? 'text-[17px] text-text-primary' : 'text-[15px] text-text-secondary'
      }`}
    >
      {value}
    </div>
  </div>
);

const Th: React.FC<{ children: React.ReactNode; align?: 'left' | 'right' }> = ({
  children,
  align = 'left',
}) => (
  <th
    className={`eyebrow px-3 py-2 text-text-muted ${align === 'right' ? 'text-right' : 'text-left'}`}
  >
    {children}
  </th>
);

const Td: React.FC<{
  children: React.ReactNode;
  align?: 'left' | 'right';
  mono?: boolean;
  muted?: boolean;
}> = ({ children, align = 'left', mono, muted }) => (
  <td
    className={`px-3 py-1.5 text-[12.5px] ${align === 'right' ? 'text-right' : 'text-left'} ${
      mono ? 'font-mono tabular-nums' : ''
    } ${muted ? 'text-text-muted' : 'text-text-secondary'}`}
  >
    {children}
  </td>
);

/** Skloňování za počtem položek. */
function polozek(n: number): string {
  if (n === 1) return 'položka';
  if (n >= 2 && n <= 4) return 'položky';
  return 'položek';
}

export default PaymentsPage;
