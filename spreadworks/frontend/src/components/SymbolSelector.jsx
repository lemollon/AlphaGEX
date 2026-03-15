import { useState, useRef, useEffect, useCallback } from 'react';

const SUPPORTED_SYMBOLS = [
  'SPY', 'QQQ', 'IWM', 'SPX', 'AAPL', 'NVDA', 'TSLA',
  'AMZN', 'META', 'GOOGL', 'MSFT', 'AMD', 'DIA', 'XSP',
];

export default function SymbolSelector({ value, onChange }) {
  const [inputVal, setInputVal] = useState(value);
  const [open, setOpen] = useState(false);
  const [focused, setFocused] = useState(false);
  const [highlighted, setHighlighted] = useState(-1);
  const [error, setError] = useState(null);
  const debounceRef = useRef(null);
  const wrapperRef = useRef(null);

  useEffect(() => {
    setInputVal(value);
  }, [value]);

  useEffect(() => {
    const handleClick = (e) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  const filtered = SUPPORTED_SYMBOLS.filter((sym) =>
    sym.startsWith(inputVal.toUpperCase())
  );

  const commitSymbol = useCallback((sym) => {
    const upper = sym.toUpperCase().trim();
    if (!upper) return;
    if (!SUPPORTED_SYMBOLS.includes(upper)) {
      setError(`"${upper}" not supported`);
      setTimeout(() => setError(null), 3000);
      return;
    }
    setError(null);
    setInputVal(upper);
    setOpen(false);
    if (upper !== value) {
      onChange(upper);
    }
  }, [value, onChange]);

  const handleInput = (e) => {
    const val = e.target.value.toUpperCase();
    setInputVal(val);
    setOpen(true);
    setHighlighted(-1);
    setError(null);

    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      if (val && SUPPORTED_SYMBOLS.includes(val)) {
        commitSymbol(val);
      }
    }, 300);
  };

  const handleKeyDown = (e) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setOpen(true);
      setHighlighted((h) => Math.min(h + 1, filtered.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setHighlighted((h) => Math.max(h - 1, 0));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (highlighted >= 0 && filtered[highlighted]) {
        commitSymbol(filtered[highlighted]);
      } else {
        commitSymbol(inputVal);
      }
    } else if (e.key === 'Escape') {
      setOpen(false);
      setInputVal(value);
    }
  };

  const handleFocus = () => {
    setFocused(true);
    setOpen(true);
    setHighlighted(-1);
  };

  const handleBlur = () => {
    setFocused(false);
    setTimeout(() => {
      if (!inputVal || inputVal.toUpperCase() !== value) {
        setInputVal(value);
      }
      setOpen(false);
    }, 150);
  };

  return (
    <div ref={wrapperRef} className="relative inline-flex items-center">
      <input
        value={inputVal}
        onChange={handleInput}
        onKeyDown={handleKeyDown}
        onFocus={handleFocus}
        onBlur={handleBlur}
        className={`bg-bg-elevated border rounded-md text-white font-bold font-[var(--font-mono)] text-sm px-2.5 py-1 w-[76px] outline-none uppercase transition-all duration-150 ${
          focused ? 'border-accent shadow-[0_0_0_2px_var(--color-accent-glow)]' : 'border-border-default'
        }`}
        spellCheck={false}
        aria-label="Symbol"
      />
      {open && filtered.length > 0 && (
        <div className="absolute top-full left-0 mt-1 bg-bg-elevated border border-border-default rounded-lg z-[100] max-h-[220px] overflow-y-auto min-w-[76px] shadow-lg animate-fade-in">
          {filtered.map((sym, i) => (
            <div
              key={sym}
              className={`px-3 py-1.5 cursor-pointer font-[var(--font-mono)] text-[13px] font-semibold transition-colors duration-150 ${
                i === highlighted ? 'text-white bg-accent/15' : 'text-text-secondary hover:bg-bg-hover'
              }`}
              onMouseDown={(e) => {
                e.preventDefault();
                commitSymbol(sym);
              }}
              onMouseEnter={() => setHighlighted(i)}
            >
              {sym}
            </div>
          ))}
        </div>
      )}
      {error && !open && (
        <span className="absolute top-full left-0 mt-1 text-sw-red text-[11px] font-[var(--font-ui)] font-medium whitespace-nowrap">
          {error}
        </span>
      )}
    </div>
  );
}

export { SUPPORTED_SYMBOLS };
