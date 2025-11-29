'use client'

import { Brain, TrendingUp, TrendingDown, Activity, Zap } from 'lucide-react'
import { MLModelStatus as MLModelStatusType, MLPrediction } from './types'

interface MLModelStatusProps {
  mlModelStatus: MLModelStatusType | null
  mlPredictions: MLPrediction[]
}

export default function MLModelStatus({ mlModelStatus, mlPredictions }: MLModelStatusProps) {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      {/* ML Model Status */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <Brain className="w-6 h-6 text-primary" />
            <h2 className="text-lg font-semibold text-text-primary">ML Model Status</h2>
          </div>
          {mlModelStatus?.is_trained && (
            <span className="px-2 py-1 bg-success/20 text-success text-xs font-semibold rounded-full">
              TRAINED
            </span>
          )}
        </div>

        {mlModelStatus ? (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="p-3 bg-background-hover rounded-lg">
                <p className="text-text-muted text-xs">Model Accuracy</p>
                <p className="text-text-primary font-bold text-lg">
                  {((mlModelStatus.accuracy || 0) * 100).toFixed(1)}%
                </p>
              </div>
              <div className="p-3 bg-background-hover rounded-lg">
                <p className="text-text-muted text-xs">Training Samples</p>
                <p className="text-text-primary font-bold text-lg">
                  {mlModelStatus.training_samples?.toLocaleString() || 'N/A'}
                </p>
              </div>
              <div className="p-3 bg-background-hover rounded-lg">
                <p className="text-text-muted text-xs">Features Used</p>
                <p className="text-text-primary font-bold text-lg">
                  {mlModelStatus.feature_count || 'N/A'}
                </p>
              </div>
              <div className="p-3 bg-background-hover rounded-lg">
                <p className="text-text-muted text-xs">Last Trained</p>
                <p className="text-text-primary font-semibold text-sm">
                  {mlModelStatus.last_trained ? new Date(mlModelStatus.last_trained).toLocaleDateString() : 'Never'}
                </p>
              </div>
            </div>

            {mlModelStatus.feature_importance && (
              <div className="mt-4">
                <p className="text-text-muted text-xs mb-2">Top Features</p>
                <div className="space-y-2">
                  {Object.entries(mlModelStatus.feature_importance || {}).slice(0, 5).map(([feature, importance]) => (
                    <div key={feature} className="flex items-center gap-2">
                      <span className="text-text-secondary text-xs w-32 truncate">{feature}</span>
                      <div className="flex-1 bg-background-primary rounded-full h-2">
                        <div
                          className="bg-primary h-2 rounded-full"
                          style={{ width: `${(importance * 100).toFixed(0)}%` }}
                        />
                      </div>
                      <span className="text-text-muted text-xs w-12 text-right">{(importance * 100).toFixed(0)}%</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="text-center py-8 text-text-secondary">
            <Brain className="w-10 h-10 text-text-muted mx-auto mb-2" />
            <p>ML model not trained yet</p>
            <p className="text-xs text-text-muted mt-1">Model will train automatically with trade data</p>
          </div>
        )}
      </div>

      {/* Recent ML Predictions */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <Zap className="w-6 h-6 text-warning" />
            <h2 className="text-lg font-semibold text-text-primary">Recent ML Predictions</h2>
          </div>
          <span className="text-xs text-text-muted">{mlPredictions.length} predictions</span>
        </div>

        {mlPredictions.length > 0 ? (
          <div className="space-y-2 max-h-64 overflow-y-auto">
            {mlPredictions.map((pred, idx) => (
              <div key={idx} className="p-3 bg-background-hover rounded-lg flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className={`w-8 h-8 rounded-full flex items-center justify-center ${
                    pred.prediction === 'bullish' || pred.predicted_direction > 0
                      ? 'bg-success/20 text-success'
                      : pred.prediction === 'bearish' || pred.predicted_direction < 0
                      ? 'bg-danger/20 text-danger'
                      : 'bg-warning/20 text-warning'
                  }`}>
                    {pred.prediction === 'bullish' || pred.predicted_direction > 0 ? (
                      <TrendingUp className="w-4 h-4" />
                    ) : pred.prediction === 'bearish' || pred.predicted_direction < 0 ? (
                      <TrendingDown className="w-4 h-4" />
                    ) : (
                      <Activity className="w-4 h-4" />
                    )}
                  </div>
                  <div>
                    <p className="text-text-primary font-semibold text-sm">
                      {pred.symbol || 'SPY'} - {pred.pattern || pred.prediction?.toUpperCase() || 'NEUTRAL'}
                    </p>
                    <p className="text-text-muted text-xs">
                      {pred.timestamp ? new Date(pred.timestamp).toLocaleString() : 'N/A'}
                    </p>
                  </div>
                </div>
                <div className="text-right">
                  <p className={`font-bold ${
                    (pred.confidence || 0) >= 70 ? 'text-success' :
                    (pred.confidence || 0) >= 50 ? 'text-warning' :
                    'text-text-muted'
                  }`}>
                    {pred.confidence?.toFixed(0) || pred.probability?.toFixed(0) || 0}%
                  </p>
                  <p className="text-text-muted text-xs">confidence</p>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-center py-8 text-text-secondary">
            <Zap className="w-10 h-10 text-text-muted mx-auto mb-2" />
            <p>No predictions yet</p>
            <p className="text-xs text-text-muted mt-1">Predictions appear during market analysis</p>
          </div>
        )}
      </div>
    </div>
  )
}
