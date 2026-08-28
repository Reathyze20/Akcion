/**
 * Vysvětlivky ke zkratkám a odborným pojmům.
 *
 * Aplikace pracuje s termíny ze tří různých světů: účetnictví, americká
 * regulace a vlastní metodika. Nikdo si je nepamatuje všechny a hádat
 * význam zkratky u čísla, podle kterého se rozhoduje o penězích, je
 * způsob, jak udělat chybu.
 *
 * Pravidla pro texty:
 *   - `expansion` je rozepsaná zkratka, nic víc.
 *   - `meaning` je jedna až dvě věty k věci, bez opisů.
 *   - Kde termín pochází z metodiky a ne z účetnictví, je to řečeno,
 *     aby se čtenář nedomníval, že jde o oborový standard.
 */

export interface GlossaryEntry {
  /** Co zkratka znamená rozepsaná. U pojmů, které zkratkou nejsou, chybí. */
  expansion?: string;
  /** Vysvětlení. Jedna až dvě věty. */
  meaning: string;
  /** Zdroj pojmu — pomáhá odlišit standard od vlastní metodiky. */
  source?: 'účetnictví' | 'regulace' | 'trh' | 'metodika';
}

export const GLOSSARY: Record<string, GlossaryEntry> = {
  /* ---- výsledek a hodnota ------------------------------------------- */

  pl: {
    expansion: 'Profit / Loss — zisk a ztráta',
    meaning:
      'Rozdíl mezi současnou tržní hodnotou pozice a částkou, za kterou byla pořízena. '
      + 'Dokud není prodána, jde o nerealizovaný výsledek.',
    source: 'účetnictví',
  },
  nerealizovanyPl: {
    meaning:
      'Zisk nebo ztráta, která existuje jen na papíře, protože pozice se stále drží. '
      + 'Realizuje se až prodejem.',
    source: 'účetnictví',
  },
  porizovaciCena: {
    meaning:
      'Průměrná cena, za kterou byly kusy pořízeny, včetně dřívějších dokupů. '
      + 'Bez ní nelze spočítat výsledek pozice ani pravidlo zdvojnásobení.',
    source: 'účetnictví',
  },
  aum: {
    expansion: 'Assets Under Management — spravovaný objem',
    meaning: 'Celková hodnota majetku ve správě, tedy pozice plus hotovost.',
    source: 'trh',
  },
  drawdown: {
    meaning:
      'Pokles z dosaženého vrcholu na dno, v procentech. Měří, jak hluboko '
      + 'portfolio zatím spadlo, ne jak si vede od začátku.',
    source: 'trh',
  },
  vaha: {
    meaning:
      'Podíl jedné pozice na celkové hodnotě portfolia. Vysoká váha znamená, '
      + 'že výsledek portfolia závisí na jedné firmě víc, než je zdrávo.',
    source: 'trh',
  },

  /* ---- identifikátory ------------------------------------------------ */

  isin: {
    expansion: 'International Securities Identification Number',
    meaning:
      'Dvanáctimístný mezinárodní identifikátor cenného papíru. Není to burzovní '
      + 'symbol — pod ISINem nelze načíst cenu ani účetní data, proto se musí '
      + 'nejdřív přeložit na ticker.',
    source: 'regulace',
  },
  ticker: {
    meaning:
      'Burzovní symbol, pod kterým se papír obchoduje. Stejná firma může mít '
      + 'na různých burzách různé tickery i různé měny.',
    source: 'trh',
  },
  adr: {
    expansion: 'American Depositary Receipt',
    meaning:
      'Stvrzenka obchodovaná v USA, která zastupuje akcie zahraniční firmy. '
      + 'Jeden kus nemusí odpovídat jedné původní akcii.',
    source: 'trh',
  },

  /* ---- regulace a podání --------------------------------------------- */

  sec: {
    expansion: 'U.S. Securities and Exchange Commission',
    meaning:
      'Americký regulátor kapitálového trhu. Firmy s americkým listingem mu '
      + 'povinně odevzdávají výsledky, takže jde o ověřený zdroj, ne o zprávu z médií.',
    source: 'regulace',
  },
  edgar: {
    expansion: 'Electronic Data Gathering, Analysis and Retrieval',
    meaning: 'Veřejná databáze, kam SEC ukládá všechna podání. Aplikace z ní čte přímo.',
    source: 'regulace',
  },
  filing10k: {
    expansion: '10-K',
    meaning: 'Výroční zpráva americké firmy. Nejúplnější dokument, který firma za rok vydá.',
    source: 'regulace',
  },
  filing10q: {
    expansion: '10-Q',
    meaning: 'Čtvrtletní zpráva americké firmy. Neprochází plným auditem.',
    source: 'regulace',
  },
  filing8k: {
    expansion: '8-K',
    meaning:
      'Hlášení mimořádné události mezi pravidelnými zprávami. Vlastní obsah bývá '
      + 'v příloze, ne v samotném formuláři.',
    source: 'regulace',
  },
  filing6k: {
    expansion: '6-K',
    meaning:
      'Průběžné hlášení zahraniční firmy s americkým listingem. Samotný formulář '
      + 'je jen krycí list; čtvrtletní čísla bývají v příloze EX-99.',
    source: 'regulace',
  },
  xbrl: {
    expansion: 'eXtensible Business Reporting Language',
    meaning:
      'Strojově čitelná podoba účetních výkazů v podání. Aplikace z ní bere čísla '
      + 'napřímo, takže se neopisují z textu.',
    source: 'regulace',
  },
  goingConcern: {
    meaning:
      'Formulace v účetní závěrce, kterou vedení přiznává vážné pochybnosti '
      + 'o schopnosti firmy pokračovat v činnosti. Patří k nejzávažnějším '
      + 'informacím, jaké lze z podání vyčíst.',
    source: 'účetnictví',
  },
  form4: {
    expansion: 'Form 4',
    meaning:
      'Hlášení o nákupu nebo prodeji akcií členem vedení či velkým akcionářem. '
      + 'Velká část se týká odměňování, ne názoru na firmu.',
    source: 'regulace',
  },

  /* ---- fondy a dostupnost -------------------------------------------- */

  etf: {
    expansion: 'Exchange Traded Fund — burzovně obchodovaný fond',
    meaning: 'Fond, s jehož podílem se obchoduje na burze jako s akcií.',
    source: 'trh',
  },
  ucits: {
    expansion: 'Undertakings for Collective Investment in Transferable Securities',
    meaning:
      'Evropský fondový standard. Fond v tomto režimu smí evropský retailový '
      + 'broker běžně nabízet, mimo něj zpravidla ne.',
    source: 'regulace',
  },
  priips: {
    expansion: 'Packaged Retail and Insurance-based Investment Products',
    meaning:
      'Evropské nařízení, které podmiňuje prodej investičního produktu drobnému '
      + 'investorovi existencí sdělení klíčových informací. Americké fondy je '
      + 'většinou nemají, a proto jsou v EU nedostupné.',
    source: 'regulace',
  },
  kid: {
    expansion: 'Key Information Document — sdělení klíčových informací',
    meaning:
      'Povinný dvoustránkový dokument podle PRIIPs. Bez něj produkt drobnému '
      + 'investorovi v EU prodat nelze.',
    source: 'regulace',
  },
  hedge: {
    meaning:
      'Pozice držená proto, aby vydělala, když hlavní portfolio ztrácí. '
      + 'Nemá vydělávat sama o sobě — má tlumit propad.',
    source: 'trh',
  },

  /* ---- čas a výnos ---------------------------------------------------- */

  rr: {
    expansion: 'rok na rok — meziročně',
    meaning:
      'Srovnání se stejným obdobím předchozího roku. U sezónních firem je to '
      + 'jediné poctivé srovnání.',
    source: 'účetnictví',
  },
  pa: {
    expansion: 'per annum — ročně',
    meaning: 'Údaj přepočtený na roční základ.',
    source: 'účetnictví',
  },
  cagr: {
    expansion: 'Compound Annual Growth Rate',
    meaning:
      'Průměrné roční tempo růstu, které by z počáteční hodnoty udělalo konečnou. '
      + 'Vyhlazuje kolísání — skutečný průběh byl skoro jistě hrbolatější.',
    source: 'trh',
  },
  slozeneUroceni: {
    meaning:
      'Výnos se počítá i z dříve připsaných výnosů, ne jen z vkladu. Proto '
      + 'křivka roste stále strměji, čím delší je období.',
    source: 'trh',
  },
  realnaHodnota: {
    meaning:
      'Částka přepočtená na dnešní kupní sílu, tedy očištěná o inflaci. '
      + 'Nominální milion za dvacet let koupí výrazně méně než dnes.',
    source: 'účetnictví',
  },

  /* ---- statistika ------------------------------------------------------ */

  sigma: {
    expansion: 'σ — směrodatná odchylka',
    meaning:
      'Míra, jak daleko je hodnota od dlouhodobého průměru. Kladná dvě sigma '
      + 'znamenají hodnotu vzácně vysokou, ne nutně neudržitelnou.',
    source: 'trh',
  },
  percentil: {
    meaning:
      'Kolik procent naměřených hodnot bylo nižších. Devadesátý percentil '
      + 'znamená, že devět z deseti měsíců za sledované období bylo levnějších.',
    source: 'trh',
  },

  /* ---- metodika --------------------------------------------------------- */

  semafor: {
    meaning:
      'Stav trhu ve čtyřech stupních, který určuje, jak spekulativní pozice se '
      + 'smí přikupovat. Odvozuje se z polohy indexu na dlouhodobém grafu.',
    source: 'metodika',
  },
  konvikcniSkore: {
    meaning:
      'Hodnocení firmy na stupnici 0 až 10 podle metodiky. Určuje cílovou váhu '
      + 'v portfoliu; bez něj aplikace pozici nezařadí a nedoporučí k ní nic.',
    source: 'metodika',
  },
  pasmo: {
    meaning:
      'Zařazení pozice podle jistoty a rizika — primární, sekundární, terciární. '
      + 'Semafor postupně zavírá pásma odspodu: čím horší stav trhu, tím '
      + 'spekulativnější pozice se nesmí přikupovat.',
    source: 'metodika',
  },
  greatFind: {
    expansion: 'Great Find — nález',
    meaning:
      'Fáze, kdy je firma objevená, ale trh ji ještě neocenil. Podle metodiky '
      + 'je to okamžik k nákupu.',
    source: 'metodika',
  },
  waitTime: {
    expansion: 'Wait Time — čekání',
    meaning:
      'Fáze, kdy se s cenou dlouho nic neděje. Kapitál je vázaný a nepracuje, '
      + 'ale teze zatím platí.',
    source: 'metodika',
  },
  goldMine: {
    expansion: 'Gold Mine — sklizeň',
    meaning:
      'Fáze, kdy trh firmu konečně ocenil a pozice rychle roste. Podle metodiky '
      + 'se v ní odebírá, ne dokupuje.',
    source: 'metodika',
  },
  zelenaLinka: {
    meaning:
      'Cena, pod kterou metodika považuje papír za levný a nákup za oprávněný.',
    source: 'metodika',
  },
  cervenaLinka: {
    meaning:
      'Cílová cena k prodeji. Kurz pod červenou linkou je běžný stav pozice, '
      + 'která na cíl ještě nedošla — není to signál k prodeji.',
    source: 'metodika',
  },
  valce: {
    expansion: 'válce — cylinders',
    meaning:
      'Známka kvality firmy od nuly do desítky: kolik jejích motorů zrovna '
      + 'běží. Nestojí na žádném webu, je to úsudek — a bez něj aplikace '
      + 'nákup nepustí.',
    source: 'metodika',
  },
  zaslouzeneSkore: {
    meaning:
      'Deset mínus válce. Laťka, přes kterou musí papír přeskočit, aby stál '
      + 'za nákup: skvělá firma se smí kupovat i draho, slabá jen hodně levně.',
    source: 'metodika',
  },
  branaNakupu: {
    meaning:
      'Řada podmínek, které musí platit současně, než aplikace navrhne nákup. '
      + 'Zastaví se na první, která neplatí, a řekne které — takže odpověď je '
      + 'vždycky konkrétní důvod, ne mlčení.',
    source: 'metodika',
  },
  zdvojnasobeni: {
    meaning:
      'Pravidlo: jakmile pozice zdvojnásobí hodnotu, prodá se polovina. '
      + 'Původní vklad je zpět a zbytek pokračuje bez rizika ztráty vlastních peněz.',
    source: 'metodika',
  },
  cashRunway: {
    expansion: 'Cash Runway — vytrvalost hotovosti',
    meaning:
      'Počet měsíců, po které firma vydrží při současném tempu pálení hotovosti, '
      + 'než bude potřebovat další peníze.',
    source: 'účetnictví',
  },

  /* ---- kalibrace vlastních skóre ------------------------------------ */

  nadvynos: {
    meaning:
      'O kolik procentních bodů papír překonal index za stejné období. '
      + 'Devítka s +5 %, když trh udělal +12 %, byla špatná rada — absolutní '
      + 'výnos by to zamaskoval, nadvýnos ne.',
    source: 'trh',
  },
  /* ---- druhý zdroj --------------------------------------------------- */

  breakoutInvestors: {
    meaning:
      'Skupina investorů kolem Marka Gomese, která u každého jména zveřejňuje '
      + 'počet podpisů a očekávaný růst. Je to druhý zdroj vedle Gomesovy '
      + 'valuace — ukazuje se, ale o velikosti pozice nerozhoduje.',
    source: 'metodika',
  },
  podpisy: {
    meaning:
      'Kolik členů skupiny se za jméno postavilo. Měří přesvědčení skupiny, '
      + 'ne kvalitu firmy — pět podpisů neznamená, že je papír levný.',
    source: 'metodika',
  },
  ocekavanyRust: {
    meaning:
      'O kolik procent podle skupiny papír vyroste. Je to jejich cílová cena '
      + 'řečená jinak: cíl se z ní dopočítá vynásobením aktuálním kurzem.',
    source: 'metodika',
  },

  sp500: {
    expansion: 'S&P 500 — index pěti set největších amerických firem',
    meaning:
      'Měřítko, proti kterému se poměřují skóre aplikace. Odpovídá tomu, co by '
      + 'člověk měl bez jakéhokoli výběru akcií.',
    source: 'trh',
  },
};

/** Klíče glosáře — pro typovou kontrolu při použití. */
export type GlossaryKey = keyof typeof GLOSSARY;

export function lookup(key: string): GlossaryEntry | undefined {
  return GLOSSARY[key];
}
