/**
 * ThesisCard Component
 * 
 * Displays the core investment thesis in an "elevator pitch" format.
 * Shows WHY we hold this stock before showing any charts or numbers.
 * 
 * Design Philosophy: Fundament before Price
 */

import React from 'react';
import { 
  Lightbulb, 
  Zap, 
  AlertTriangle,
  Calendar,
  ChevronDown,
  ChevronUp
} from 'lucide-react';

export interface ThesisCardProps {
  thesisNarrative: string | null;
  edge: string | null;
  catalysts: string | null;
  nextCatalyst: string | null;
  risks: string | null;
  primaryCatalyst: string | null;
  catalystDate: string | null;
}

export const ThesisCard: React.FC<ThesisCardProps> = ({
  thesisNarrative,
  edge,
  catalysts,
  nextCatalyst,
  risks,
  primaryCatalyst,
  catalystDate,
}) => {
  const [isExpanded, setIsExpanded] = React.useState(false);
  
  // Determine if we have enough content to show
  const hasContent = thesisNarrative || edge || catalysts;
  
  if (!hasContent) {
    return (
      <div className="card p-4 border-l-4 border-text-muted">
        <div className="flex items-center gap-2 text-text-muted">
          <Lightbulb className="w-5 h-5" />
          <span className="text-sm italic">Investiční teze zatím nebyla definována.</span>
        </div>
      </div>
    );
  }
  
  return (
    <div className="card p-0 overflow-hidden">
      {/* Main Thesis - Always Visible */}
      <div className="p-4 border-l-4 border-accent bg-gradient-to-r from-accent/5 to-transparent">
        <div className="flex items-start gap-3">
          <Lightbulb className="w-5 h-5 text-accent flex-shrink-0 mt-0.5" />
          <div className="flex-1">
            <h3 className="text-sm font-semibold text-accent mb-2">
              Investiční teze
            </h3>
            <p className="text-text-primary leading-relaxed">
              {thesisNarrative || edge || 'Teze nebyla specifikována.'}
            </p>
          </div>
        </div>
      </div>
      
      {/* Next Catalyst - Prominent if present */}
      {(nextCatalyst || primaryCatalyst) && (
        <div className="px-4 py-3 bg-positive/10 border-t border-border flex items-center gap-3">
          <Calendar className="w-4 h-4 text-positive flex-shrink-0" />
          <div>
            <span className="text-xs text-positive font-medium">PŘÍŠTÍ KATALYZÁTOR: </span>
            <span className="text-sm text-text-primary font-medium">
              {nextCatalyst || primaryCatalyst}
              {catalystDate && (
                <span className="text-text-secondary ml-2">({catalystDate})</span>
              )}
            </span>
          </div>
        </div>
      )}
      
      {/* Expandable Details */}
      {(catalysts || risks) && (
        <>
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            className="w-full px-4 py-2 bg-primary-card/50 border-t border-border
                       flex items-center justify-between text-sm text-text-secondary
                       hover:bg-primary-card transition-colors"
          >
            <span>{isExpanded ? 'Skrýt detaily' : 'Zobrazit katalyzátory a rizika'}</span>
            {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </button>
          
          {isExpanded && (
            <div className="border-t border-border">
              {/* Edge - if different from thesis */}
              {edge && edge !== thesisNarrative && (
                <div className="p-4 border-b border-border">
                  <div className="flex items-start gap-2">
                    <Zap className="w-4 h-4 text-accent flex-shrink-0 mt-0.5" />
                    <div>
                      <h4 className="text-xs font-semibold text-accent mb-1">Informační výhoda (Edge)</h4>
                      <p className="text-sm text-text-primary">{edge}</p>
                    </div>
                  </div>
                </div>
              )}
              
              {/* Catalysts */}
              {catalysts && (
                <div className="p-4 border-b border-border bg-positive/5">
                  <div className="flex items-start gap-2">
                    <Zap className="w-4 h-4 text-positive flex-shrink-0 mt-0.5" />
                    <div>
                      <h4 className="text-xs font-semibold text-positive mb-1">Katalyzátory</h4>
                      <p className="text-sm text-text-primary whitespace-pre-wrap">{catalysts}</p>
                    </div>
                  </div>
                </div>
              )}
              
              {/* Risks */}
              {risks && (
                <div className="p-4 bg-negative/5">
                  <div className="flex items-start gap-2">
                    <AlertTriangle className="w-4 h-4 text-negative flex-shrink-0 mt-0.5" />
                    <div>
                      <h4 className="text-xs font-semibold text-negative mb-1">Rizika</h4>
                      <p className="text-sm text-text-primary whitespace-pre-wrap">{risks}</p>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
};

export default ThesisCard;
