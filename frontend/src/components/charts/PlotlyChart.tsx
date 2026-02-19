'use client'

// Shared Plotly component using the minimal distribution (plotly.js-dist-min)
// instead of the full plotly.js (~3.5MB → ~1MB savings)
import createPlotlyComponent from 'react-plotly.js/factory'
import Plotly from 'plotly.js-dist-min'

const Plot = createPlotlyComponent(Plotly)

export default Plot
