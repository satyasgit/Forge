import axios from 'axios';
import type {
  TemplateListResponse,
  TemplateDetailResponse,
  ValidationResponse,
  PipelinePreviewResponse,
  PipelineRunResponse,
  RunPipelineRequest,
  PipelineConfig,
} from './types';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

const api = axios.create({
  baseURL: API_BASE,
  headers: {
    'Content-Type': 'application/json',
  },
});

export async function getTemplates(): Promise<TemplateListResponse> {
  const response = await api.get<TemplateListResponse>('/pipelines/templates');
  return response.data;
}

export async function getTemplate(name: string): Promise<TemplateDetailResponse> {
  const response = await api.get<TemplateDetailResponse>(`/pipelines/templates/${name}`);
  return response.data;
}

export async function validateConfig(
  config: PipelineConfig
): Promise<ValidationResponse> {
  const response = await api.post<ValidationResponse>('/pipelines/validate', {
    config,
  });
  return response.data;
}

export async function previewPipeline(
  config: PipelineConfig
): Promise<PipelinePreviewResponse> {
  const response = await api.post<PipelinePreviewResponse>('/pipelines/preview', config);
  return response.data;
}

export async function runPipeline(request: RunPipelineRequest): Promise<PipelineRunResponse> {
  const response = await api.post<PipelineRunResponse>('/pipelines/run', request);
  return response.data;
}

export async function getHealth() {
  const response = await api.get('/pipelines/health');
  return response.data;
}

export default api;
