import '@testing-library/jest-dom';
import { render, screen, waitFor } from '@testing-library/react';
import PredictiveMaintenancePage from '@/app/predictive-maintenance/page';
import * as api from '@/lib/api';

jest.mock('@/lib/api');

const mockedApi = api as jest.Mocked<typeof api>;

describe('predictive ML observability', () => {
  beforeEach(() => {
    mockedApi.listPredictions.mockResolvedValue([]);
    mockedApi.listMaintenanceRecommendations.mockResolvedValue([]);
    mockedApi.listAnomalies.mockResolvedValue([]);
    mockedApi.listDiagnoses.mockResolvedValue([]);
    mockedApi.listMLModels.mockResolvedValue([
      {
        id: 7,
        name: 'bearing risk',
        task_type: 'failure_risk',
        algorithm: 'logistic_regression',
        version: 'failure-risk-v1',
        dataset_version_id: 3,
        training_run_id: 5,
        feature_schema_version: 'bearing-features-v1',
        git_commit_sha: 'a'.repeat(40),
        artifact_sha256: 'b'.repeat(64),
        status: 'staging',
        is_production: false,
        created_at: '2026-08-03T00:00:00Z',
      },
    ]);
    mockedApi.listMLPredictionRecords.mockResolvedValue([
      {
        id: 11,
        equipment_id: 1,
        model_version_id: 7,
        prediction_type: 'failure_risk',
        prediction: '1',
        probability: 0.82,
        confidence: 0.9,
        prediction_horizon: 'next 30 samples',
        feature_timestamp_start: '2026-08-03T00:00:00Z',
        feature_timestamp_end: '2026-08-03T00:01:00Z',
        feature_schema_version: 'bearing-features-v1',
        top_contributing_features: [
          { name: 'rms', contribution: 0.72 },
        ],
        created_at: '2026-08-03T00:01:01Z',
      },
    ]);
  });

  it('shows model lineage, probability, and model-derived feature evidence', async () => {
    render(<PredictiveMaintenancePage />);

    await waitFor(() => {
      expect(screen.getByTestId('ml-observability')).toBeInTheDocument();
    });
    expect(screen.getByText('failure-risk-v1')).toBeInTheDocument();
    expect(screen.getByText('staging')).toBeInTheDocument();
    expect(screen.getByText('82.0%')).toBeInTheDocument();
    expect(screen.getByLabelText('Top contributing features')).toHaveTextContent('rms: 0.720');
    expect(screen.getByText(/Operational Health Score/)).toBeInTheDocument();
  });
});
