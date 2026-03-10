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
    background: '#12121e',
    border: '1px solid #2a2a40',
    borderRadius: 3,
    color: '#fff',
    fontWeight: 700,
    fontFamily: "'Courier New', monospace",
    fontSize: 13,
    padding: '3px 8px',
    width: 72,
    outline: 'none',
    textTransform: 'uppercase',
  },
  inputFocused: {
    borderColor: '#448aff',
  },
  dropdown: {
    position: 'absolute',
    top: '100%',
    left: 0,
    marginTop: 2,
    background: '#12121e',
    border: '1px solid #2a2a40',
    borderRadius: 3,
    zIndex: 100,
    maxHeight: 200,
    overflowY: 'auto',
    minWidth: 72,
    boxShadow: '0 4px 12px rgba(0,0,0,0.5)',
  },
  option: (isHighlighted) => ({
    padding: '5px 10px',
    cursor: 'pointer',
    fontFamily: "'Courier New', monospace",
    fontSize: 12,
    fontWeight: 600,
    color: isHighlighted ? '#fff' : '#aaa',
    background: isHighlighted ? '#448aff33' : 'transparent',
  }),
  error: {
    color: '#ef5350',
    fontSize: 10,
    fontFamily: "'Courier New', monospace",
    position: 'absolute',
    top: '100%',
    left: 0,
    marginTop: 2,
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

  // Sync external value changes
  useEffect(() => {
    setInputVal(value);
  }, [value]);

  // Close dropdown on outside click
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
      setInputVal(value); // revert
    }
  };

  const handleFocus = () => {
    setFocused(true);
    setOpen(true);
    setHighlighted(-1);
  };

  const handleBlur = () => {
    setFocused(false);
    // Small delay to allow click on dropdown item
    setTimeout(() => {
      if (!inputVal || inputVal.toUpperCase() !== value) {
        setInputVal(value); // revert on blur if not committed
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
                e.preventDefault(); // prevent blur
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
