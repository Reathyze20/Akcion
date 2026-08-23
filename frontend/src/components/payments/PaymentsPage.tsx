/**
 * Platby — dvě skupiny knih, pod sebou na jedné stránce.
 *
 * Skupina „Splácení" a skupina „Placení" fungují stejně — obě jsou seznam
 * knih (kdysi pevně pojmenovaných „Společné splácení", „Platby Míša" atd.),
 * ke kterým lze tlačítkem „Nová kniha" přidat další. Dřív bylo pět knih
 * napevno zadrátovaných jako pět různých proměnných v InvestmentTerminal;
 * teď je to jeden seznam na skupinu, takže přibýt může kolik knih je potřeba.
 *
 * Souhrn (měsíčně, zbývá uhradit, celkový dluh, splaceno) patří vždycky
 * jen ke své knize — každá kniha skupiny „Splácení" počítá tahle čtyři
 * čísla ze svých vlastních položek, ne ze všech knih dohromady.
 *
 * Knihy skupiny „Placení" mají stejný půdorys sloupců (Splátka, Číslo
 * účtu, VS, Informace), aby šly zarovnat pod sebe napříč knihami — proto
 * mají pevnou šířku sloupců místo šířky podle obsahu. Vpravo tak zbývá
 * volné místo u kratších knih; to je záměr, ne chyba.
 *
 * Položky v každé knize se řadí abecedně podle názvu, ne podle pořadí
 * přidání — jinak by nová položka skočila na konec bez ohledu na to, kam
 * abecedně patří.
 *
 * Data i formuláře zůstávají v InvestmentTerminal. Tahle komponenta jen
 * kreslí — nedrží stav, nezapisuje do localStorage, a proto nemůže o nic
 * přijít.
 */

import React, { useMemo } from 'react';
import { Edit3, Plus, Settings2 } from 'lucide-react';

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

export interface PaymentBook {
  id: string;
  name: string;
  items: PaymentRecord[];
}

export type PaymentGroupKind = 'debt' | 'payment';

interface PaymentsPageProps {
  debtBooks: PaymentBook[];
  paymentBooks: PaymentBook[];
  formatCurrency: (value: number, currency?: string) => string;
  onAddItem: (groupKind: PaymentGroupKind, bookId: string) => void;
  onEditItem: (groupKind: PaymentGroupKind, bookId: string, item: PaymentRecord) => void;
  onAddBook: (groupKind: PaymentGroupKind) => void;
  onManageBook: (groupKind: PaymentGroupKind, bookId: string) => void;
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

/** Abecední pořadí položek podle názvu, česká kolace (Š za S, ne za Z). */
function sortByName(items: PaymentRecord[]): PaymentRecord[] {
  return [...items].sort((a, b) => a.name.localeCompare(b.name, 'cs'));
}

export const PaymentsPage: React.FC<PaymentsPageProps> = ({
  debtBooks,
  paymentBooks,
  formatCurrency,
  onAddItem,
  onEditItem,
  onAddBook,
  onManageBook,
}) => {
  return (
    <div className="flex h-full min-h-0 flex-col gap-5 overflow-y-auto pr-0.5">
      <BookGroup
        title="Splácení"
        kind="debt"
        books={debtBooks}
        formatCurrency={formatCurrency}
        onAddItem={(bookId) => onAddItem('debt', bookId)}
        onEditItem={(bookId, item) => onEditItem('debt', bookId, item)}
        onAddBook={() => onAddBook('debt')}
        onManageBook={(bookId) => onManageBook('debt', bookId)}
      />
      <BookGroup
        title="Placení"
        kind="payment"
        books={paymentBooks}
        formatCurrency={formatCurrency}
        onAddItem={(bookId) => onAddItem('payment', bookId)}
        onEditItem={(bookId, item) => onEditItem('payment', bookId, item)}
        onAddBook={() => onAddBook('payment')}
        onManageBook={(bookId) => onManageBook('payment', bookId)}
      />
    </div>
  );
};

/* -------------------------------------------------------------------------
   Skupina knih — Splácení nebo Placení. Obě fungují stejně: nadpis
   skupiny, tlačítko na novou knihu, a knihy pod sebou.
------------------------------------------------------------------------- */

const BookGroup: React.FC<{
  title: string;
  kind: PaymentGroupKind;
  books: PaymentBook[];
  formatCurrency: (value: number, currency?: string) => string;
  onAddItem: (bookId: string) => void;
  onEditItem: (bookId: string, item: PaymentRecord) => void;
  onAddBook: () => void;
  onManageBook: (bookId: string) => void;
}> = ({ title, kind, books, formatCurrency, onAddItem, onEditItem, onAddBook, onManageBook }) => (
  <div className="flex shrink-0 flex-col gap-2">
    <div className="flex items-center justify-between px-0.5">
      <span className="eyebrow text-text-muted">{title}</span>
      <button
        onClick={onAddBook}
        className="flex items-center gap-1.5 rounded-button border border-border px-2.5 py-1 text-[12px] text-text-secondary transition-colors hover:bg-surface-hover hover:text-text-primary"
      >
        <Plus className="h-3.5 w-3.5" />
        Nová tabulka {title}
      </button>
    </div>

    {books.length === 0 ? (
      <div className="flex flex-col items-center justify-center gap-1 rounded-card border border-dashed border-border px-4 py-6 text-center">
        <p className="text-[12px] text-text-muted">Zatím žádná kniha.</p>
      </div>
    ) : (
      books.map((book) => (
        <LedgerSection
          key={book.id}
          book={book}
          kind={kind}
          formatCurrency={formatCurrency}
          onAdd={() => onAddItem(book.id)}
          onEdit={(item) => onEditItem(book.id, item)}
          onManage={() => onManageBook(book.id)}
        />
      ))
    )}
  </div>
);

/* -------------------------------------------------------------------------
   Sekce jedné knihy — hlavička (nadpis + částka) a tabulka. Knihy skupiny
   Placení sdílejí pevný půdorys sloupců (colgroup), aby se sloupce
   Splátka/Číslo účtu/VS/Informace zarovnaly napříč knihami.
------------------------------------------------------------------------- */

const LedgerSection: React.FC<{
  book: PaymentBook;
  kind: PaymentGroupKind;
  formatCurrency: (value: number, currency?: string) => string;
  onAdd: () => void;
  onEdit: (item: PaymentRecord) => void;
  onManage: () => void;
}> = ({ book, kind, formatCurrency, onAdd, onEdit, onManage }) => {
  const items = useMemo(() => sortByName(book.items), [book.items]);
  const monthly = monthlyTotal(items);
  /* Souhrn patří jen téhle knize — počítá se výhradně z jejích vlastních
     položek. Dvě knihy typu Splácení tak mají každá svá čtyři čísla, ne
     jeden součet za celou skupinu. */
  const debtStats =
    kind === 'debt' && items.length > 0
      ? {
          remaining: items.reduce((sum, d) => sum + remainingOn(d), 0),
          total: items.reduce((sum, d) => sum + num(d.amount), 0),
          paid: items.reduce((sum, d) => sum + paidSoFar(d), 0),
        }
      : null;

  return (
    <div className="flex shrink-0 flex-col overflow-hidden rounded-card border border-border bg-surface-raised">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border-subtle py-2 pr-3">
        {/* Název a odznak sedí ve stejných dvou sloupcích (14rem/8rem) jako
            tabulka pod nimi — Splátka tak vždycky začíná na stejném x jako
            odznak, ať je název knihy jakkoli dlouhý nebo krátký. */}
        <div
          className="grid items-center"
          style={kind === 'payment' ? { gridTemplateColumns: '14rem 8rem' } : undefined}
        >
          <div className="px-3">
            <h2 className="text-[20px] font-semibold text-text-primary">{book.name}</h2>
          </div>
          {kind === 'payment' && (
            <div className="px-3">
              <span className="inline-flex w-fit items-baseline rounded-button border border-border px-2 py-1">
                <span className="font-mono text-[13px] tabular-nums text-text-primary">
                  {formatCurrency(monthly)}
                </span>
              </span>
            </div>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={onManage}
            className="flex items-center gap-1.5 rounded-button border border-border px-2.5 py-1 text-[12px] text-text-secondary transition-colors hover:bg-surface-hover hover:text-text-primary"
          >
            <Settings2 className="h-3.5 w-3.5" />
            Upravit
          </button>
          <button
            onClick={onAdd}
            className="flex items-center gap-1.5 rounded-button border border-border px-2.5 py-1 text-[12px] text-text-secondary transition-colors hover:bg-surface-hover hover:text-text-primary"
          >
            <Plus className="h-3.5 w-3.5" />
            Přidat platbu
          </button>
        </div>
      </div>

      {debtStats && (
        <div className="grid grid-cols-2 gap-px border-b border-border-subtle bg-border sm:grid-cols-4">
          <SummaryCell label="Měsíčně" value={formatCurrency(monthly)} hint="Součet splátek této knihy." strong />
          <SummaryCell
            label="Zbývá uhradit"
            value={formatCurrency(debtStats.remaining)}
            hint="Po odečtení dosud zaplacených splátek."
          />
          <SummaryCell
            label="Celkový dluh"
            value={formatCurrency(debtStats.total)}
            hint="Původní výše závazků v této knize."
          />
          <SummaryCell
            label="Splaceno"
            value={formatCurrency(debtStats.paid)}
            hint="Splátky × měsíce od první splátky."
          />
        </div>
      )}

      {items.length === 0 ? (
        /* Prázdný stav na jednu řádku. Kolečko 80 × 80 px se zelenou
           fajfkou tu dřív slavilo, že se nic neeviduje — a zabíralo
           výšku pěti záznamů. */
        <div className="flex flex-col items-center justify-center gap-2 px-4 py-8 text-center">
          <p className="text-[13px] text-text-secondary">Zatím tu nic není.</p>
          <p className="max-w-sm text-[12px] text-text-muted">
            {kind === 'debt'
              ? 'Hypotéka, leasing, půjčka — cokoli, co se splácí po měsících.'
              : 'Pravidelná měsíční platba.'}
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          {/* Název/Splátka/Číslo účtu/VS mají v obou knihovnách stejnou
              pevnou šířku (colgroup), takže se zarovnají pod sebe napříč
              Splácením i Placením. Zbytek sloupců u Splácení (Částka, Zbývá,
              Splaceno, 1. splátka, Komu) na nic zarovnaný být nemusí — v
              Placení neexistují. */}
          <table className="w-full table-fixed">
            <colgroup>
              <col className="w-56" />
              <col className="w-32" />
              <col className="w-56" />
              <col className="w-32" />
              {kind === 'debt' && (
                <>
                  <col className="w-36" />
                  <col className="w-36" />
                  <col className="w-36" />
                  <col className="w-28" />
                  <col className="w-40" />
                </>
              )}
              {/* Informace nemá šířku — je to jediný sloupec, do kterého se
                  vlije zbylá šířka karty. Musí být vždycky přítomný, i u
                  knihy bez jediné poznámky: bez pružného sloupce by
                  `table-fixed` roztáhl proporčně všechny pevné sloupce a
                  Splátka/Číslo účtu/VS by se rozjely s Placením. */}
              <col />
              <col className="w-10" />
            </colgroup>
            <thead>
              <tr className="border-b border-border">
                <Th>Název</Th>
                <Th align="right">Splátka</Th>
                <Th>Číslo účtu</Th>
                <Th>VS</Th>
                {kind === 'debt' && <Th align="right">Částka</Th>}
                {kind === 'debt' && <Th align="right">Zbývá</Th>}
                {kind === 'debt' && <Th align="right">Splaceno</Th>}
                {kind === 'debt' && <Th>1. splátka</Th>}
                {kind === 'debt' && <Th>Komu</Th>}
                <Th>Informace</Th>
                <Th align="right"> </Th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr
                  key={item.id}
                  className="group border-b border-border-subtle transition-colors hover:bg-surface-hover"
                >
                  <Td>
                    <span className="text-[13px] text-text-primary">{item.name || '—'}</span>
                  </Td>

                  <Td align="right" mono>
                    {item.monthlyPayment ? formatCurrency(num(item.monthlyPayment)) : '—'}
                  </Td>

                  <Td mono muted>{item.accountNumber || '—'}</Td>
                  <Td mono muted>{item.variableSymbol || '—'}</Td>

                  {kind === 'debt' && (
                    <Td align="right" mono>
                      {item.amount ? formatCurrency(num(item.amount)) : '—'}
                    </Td>
                  )}
                  {kind === 'debt' && (
                    <Td align="right" mono>
                      {item.amount ? formatCurrency(remainingOn(item)) : '—'}
                    </Td>
                  )}
                  {kind === 'debt' && (
                    <Td align="right" mono muted>
                      {item.date ? formatCurrency(paidSoFar(item)) : '—'}
                    </Td>
                  )}
                  {kind === 'debt' && (
                    <Td muted>
                      {item.date && !Number.isNaN(new Date(item.date).getTime())
                        ? new Date(item.date).toLocaleDateString('cs-CZ')
                        : '—'}
                    </Td>
                  )}
                  {kind === 'debt' && <Td muted>{item.creditor || '—'}</Td>}

                  <Td muted>
                    <span className="block break-words" title={item.note}>
                      {item.note || '—'}
                    </span>
                  </Td>

                  <Td align="right">
                    <button
                      onClick={() => onEdit(item)}
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

export default PaymentsPage;
