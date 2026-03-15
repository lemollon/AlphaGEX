import { useState, useRef, useEffect, useCallback } from 'react';

const SUPPORTED_SYMBOLS = [
  'SPY', 'QQQ', 'IWM', 'SPX', 'AAPL', 'NVDA', 'TSLA',
  'AMZN', 'META', 'GOOGL', 'MSFT', 'AMD', 'DIA', 'XSP',
];

const s = {
  wrapper: {
    position: 'relative',
    display: 'inline-flex',
    alignItems: 'center',
  },
  input: {
    background: 'var(--bg-elevated)',
    border: '1px solid var(--border-default)',
    borderRadius: 'var(--radius-sm)',
    color: '#fff',
    fontWeight: 700,
    fontFamily: 'var(--font-mono)',
    fontSize: 14,
    padding: '4px 10px',
    width: 76,
    outline: 'none',
    textTransform: 'uppercase',
    transition: 'border-color var(--transition-fast), box-shadow var(--transition-fast)',
  },
  inputFocused: {
    borderColor: 'var(--accent)',
    boxShadow: '0 0 0 2px var(--accent-glow)',
  },
  dropdown: {
    position: 'absolute',
    top: '100%',
    left: 0,
    marginTop: 4,
    background: 'var(--bg-elevated)',
    border: '1px solid var(--border-default)',
    borderRadius: 'var(--radius-md)',
    zIndex: 100,
    maxHeight: 220,
    overflowY: 'auto',
    minWidth: 76,
    boxShadow: 'var(--shadow-lg)',
    animation: 'sw-fadeIn 0.15s ease',
  },
  option: (isHighlighted) => ({
    padding: '7px 12px',
    cursor: 'pointer',
    fontFamily: 'var(--font-mono)',
    fontSize: 13,
    fontWeight: 600,
    color: isHighlighted ? '#fff' : 'var(--text-secondary)',
    background: isHighlighted ? 'rgba(68, 138, 255, 0.15)' : 'transparent',
    transition: 'background var(--transition-fast)',
  }),
  error: {
    color: 'var(--red)',
    fontSize: 11,
    fontFamily: 'var(--font-ui)',
    fontWeight: 500,
    position: 'absolute',
    top: '100%',
    left: 0,
    marginTop: 4,
    whiteSpace: 'nowrap',
  },
};

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
    <div ref={wrapperRef} style={s.wrapper}>
      <input
        value={inputVal}
        onChange={handleInput}
        onKeyDown={handleKeyDown}
        onFocus={handleFocus}
        onBlur={handleBlur}
        style={{ ...s.input, ...(focused ? s.inputFocused : {}) }}
        spellCheck={false}
        aria-label="Symbol"
      />
      {open && filtered.length > 0 && (
        <div style={s.dropdown}>
          {filtered.map((sym, i) => (
            <div
              key={sym}
              style={s.option(i === highlighted)}
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
      {error && !open && <span style={s.error}>{error}</span>}
    </div>
  );
}

export { SUPPORTED_SYMBOLS };
