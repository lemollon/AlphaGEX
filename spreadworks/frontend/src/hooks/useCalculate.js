import { useState, useCallback } from 'react';

const API_URL = import.meta.env.VITE_API_URL || '';

export default function useCalculate() {
  const [calcResult, setCalcResult] = useState(null);
  const [calcLoading, setCalcLoading] = useState(false);
  const [calcError, setCalcError] = useState(null);

  const calculate = useCallback(async (payload) => {
    setCalcLoading(true);
    setCalcResult(null);
    setCalcError(null);
    try {
      const res = await fetch(`${API_URL}/api/spreadworks/calculate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || 'Calculation failed');
      }
      const data = await res.json();
      setCalcResult(data);
      return data;
    } catch (err) {
      setCalcError(err.message);
      return null;
    } finally {
      setCalcLoading(false);
    }
  }, []);

  const clearResult = useCallback(() => {
    setCalcResult(null);
    setCalcError(null);
  }, []);

  return { calcResult, calcLoading, calcError, calculate, clearResult };
}
