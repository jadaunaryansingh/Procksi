# Frontend-Backend Integration Guide

**Complete guide for connecting your frontend application to the Repository Analyzer API**

---

## 📋 Table of Contents

1. [Overview](#overview)
2. [API Configuration](#api-configuration)
3. [Authentication & Security](#authentication--security)
4. [Complete API Reference](#complete-api-reference)
5. [Request/Response Examples](#requestresponse-examples)
6. [Error Handling](#error-handling)
7. [TypeScript Integration](#typescript-integration)
8. [React Integration Examples](#react-integration-examples)
9. [WebSocket/Polling for Real-time Updates](#websocketpolling-for-real-time-updates)
10. [Testing](#testing)
11. [Production Checklist](#production-checklist)

---

## 🎯 Overview

### Architecture

```
Frontend (React/Next.js/Vue)
  ↓
API Client (axios/fetch)
  ↓
Nginx (public :80/:443)
  ↓
FastAPI Backend (http://localhost:3000, private)
  ↓
Supabase PostgreSQL Database
```

### Base URLs

| Environment | URL | 
|-------------|-----|
| Local Development | `http://localhost:8080` (frontend) + `/api` (proxy) |
| EC2 Production | `http://your-server-ip` (same origin) |
| With Domain | `https://yourapp.com` (same origin) |

---

## 🔧 API Configuration

### 1. Environment Variables

Create `.env.local` (Next.js) or `.env` (React/Vue):

```env
# API Configuration
# Leave empty to use same-origin /api paths
NEXT_PUBLIC_API_URL=
NEXT_PUBLIC_API_TIMEOUT=30000
NEXT_PUBLIC_ENABLE_LOGGING=true

# Optional: If you add API key authentication later
NEXT_PUBLIC_API_KEY=your_api_key_here
```

### 2. Axios Client Setup

**`lib/api/client.ts`**
```typescript
import axios, { AxiosInstance, AxiosError } from 'axios';

// API Configuration
const API_CONFIG = {
  baseURL: process.env.NEXT_PUBLIC_API_URL || '',
  timeout: parseInt(process.env.NEXT_PUBLIC_API_TIMEOUT || '30000'),
  headers: {
    'Content-Type': 'application/json',
  },
};

// Create axios instance
export const apiClient: AxiosInstance = axios.create(API_CONFIG);

// Request interceptor (logging, auth tokens, etc.)
apiClient.interceptors.request.use(
  (config) => {
    // Add timestamp to requests
    config.headers['X-Request-Time'] = new Date().toISOString();
    
    // Add auth token if available
    const token = localStorage.getItem('auth_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    
    if (process.env.NEXT_PUBLIC_ENABLE_LOGGING === 'true') {
      console.log(`[API Request] ${config.method?.toUpperCase()} ${config.url}`, config.data);
    }
    
    return config;
  },
  (error) => {
    console.error('[API Request Error]', error);
    return Promise.reject(error);
  }
);

// Response interceptor (error handling, logging)
apiClient.interceptors.response.use(
  (response) => {
    if (process.env.NEXT_PUBLIC_ENABLE_LOGGING === 'true') {
      console.log(`[API Response] ${response.config.url}`, response.data);
    }
    return response;
  },
  (error: AxiosError) => {
    // Handle different error types
    if (error.response) {
      // Server responded with error status
      console.error('[API Error Response]', {
        status: error.response.status,
        data: error.response.data,
        url: error.config?.url,
      });
    } else if (error.request) {
      // Request made but no response
      console.error('[API No Response]', error.message);
    } else {
      // Error in request configuration
      console.error('[API Config Error]', error.message);
    }
    
    return Promise.reject(error);
  }
);

export default apiClient;
```

### 3. Fetch API Alternative

If you prefer native `fetch`:

**`lib/api/fetchClient.ts`**
```typescript
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || '';

interface FetchOptions extends RequestInit {
  params?: Record<string, string | number>;
}

async function apiFetch<T>(
  endpoint: string,
  options: FetchOptions = {}
): Promise<T> {
  const { params, ...fetchOptions } = options;
  
  // Build URL with query params
  let url = `${API_BASE_URL}${endpoint}`;
  if (params) {
    const queryString = new URLSearchParams(
      Object.entries(params).map(([k, v]) => [k, String(v)])
    ).toString();
    url += `?${queryString}`;
  }
  
  // Default headers
  const headers = {
    'Content-Type': 'application/json',
    ...fetchOptions.headers,
  };
  
  try {
    const response = await fetch(url, { ...fetchOptions, headers });
    
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || `HTTP ${response.status}`);
    }
    
    return await response.json();
  } catch (error) {
    console.error('[API Fetch Error]', error);
    throw error;
  }
}

export default apiFetch;
```

---

## 🔐 Authentication & Security

### CORS Configuration

With Nginx serving the frontend and proxying `/api` on the same origin,
frontend requests are same-origin and do not require CORS.

If you deploy the frontend on a different domain, set explicit origins:
```env
CORS_ORIGINS=https://yourapp.com,https://www.yourapp.com
```

### Request Headers

```typescript
const headers = {
  'Content-Type': 'application/json',
  'X-Request-ID': generateRequestId(), // Optional: for tracking
  'Accept': 'application/json',
};
```

### Rate Limiting

Currently no rate limiting. Recommended to implement on frontend:

```typescript
import pLimit from 'p-limit';

const limit = pLimit(5); // Max 5 concurrent requests

const promises = repositories.map(repo => 
  limit(() => analyzeRepository(repo.id))
);

await Promise.all(promises);
```

---

## 📡 Complete API Reference

### Health & Status

#### `GET /health`
Check API health status

**Request:**
```typescript
const checkHealth = async () => {
  const response = await apiClient.get('/health');
  return response.data;
};
```

**Response:**
```json
{
  "status": "ok",
  "timestamp": "2026-01-09T10:30:00Z"
}
```

---

### Statistics

#### `GET /api/stats`
Get platform statistics

**Request:**
```typescript
interface StatsResponse {
  totalProjects: number;
  totalAnalyses: number;
  completedAnalyses: number;
  pendingAnalyses: number;
  failedAnalyses: number;
  avgScore: number;
}

const getStats = async (): Promise<StatsResponse> => {
  const response = await apiClient.get('/api/stats');
  return response.data;
};
```

**Response:**
```json
{
  "totalProjects": 42,
  "totalAnalyses": 156,
  "completedAnalyses": 145,
  "pendingAnalyses": 8,
  "failedAnalyses": 3,
  "avgScore": 78.5
}
```

---

### Projects

#### `GET /api/projects`
List all projects with pagination

**Request:**
```typescript
interface Project {
  id: number;
  projectId: string;
  name: string;
  description: string | null;
  repoUrl: string;
  language: string | null;
  stars: number | null;
  forks: number | null;
  openIssues: number | null;
  teamSize: number | null;
  createdAt: string;
  updatedAt: string;
}

interface ProjectsResponse {
  projects: Project[];
  total: number;
  page: number;
  perPage: number;
}

const getProjects = async (
  page: number = 1,
  perPage: number = 10
): Promise<ProjectsResponse> => {
  const response = await apiClient.get('/api/projects', {
    params: { page, per_page: perPage }
  });
  return response.data;
};
```

**Response:**
```json
{
  "projects": [
    {
      "id": 1,
      "projectId": "proj_abc123",
      "name": "awesome-project",
      "description": "An awesome repository",
      "repoUrl": "https://github.com/user/awesome-project",
      "language": "Python",
      "stars": 1234,
      "forks": 56,
      "openIssues": 12,
      "teamSize": 5,
      "createdAt": "2026-01-01T10:00:00Z",
      "updatedAt": "2026-01-09T10:00:00Z"
    }
  ],
  "total": 42,
  "page": 1,
  "perPage": 10
}
```

#### `GET /api/projects/{project_id}`
Get detailed project information

**Request:**
```typescript
interface ProjectDetail extends Project {
  techStack: TechStack[];
  issues: Issue[];
  teamMembers: TeamMember[];
  latestScore: Score | null;
}

interface TechStack {
  id: number;
  technology: string;
  category: string;
  version: string | null;
}

interface Issue {
  id: number;
  title: string;
  status: string;
  severity: string;
  category: string;
  description: string;
}

interface TeamMember {
  id: number;
  name: string;
  role: string;
  commits: number;
  linesAdded: number;
  linesDeleted: number;
}

interface Score {
  totalScore: number;
  algorithmsScore: number;
  llmScore: number;
  qualityScore: number;
  securityScore: number;
  productScore: number;
  timestamp: string;
}

const getProjectDetails = async (projectId: string): Promise<ProjectDetail> => {
  const response = await apiClient.get(`/api/projects/${projectId}`);
  return response.data;
};
```

#### `POST /api/projects`
Create a new project

**Request:**
```typescript
interface CreateProjectRequest {
  name: string;
  repoUrl: string;
  description?: string;
}

const createProject = async (data: CreateProjectRequest): Promise<Project> => {
  const response = await apiClient.post('/api/projects', data);
  return response.data;
};
```

**Example:**
```typescript
const newProject = await createProject({
  name: "my-awesome-app",
  repoUrl: "https://github.com/username/my-awesome-app",
  description: "A revolutionary application"
});
```

---

### Analysis

#### `POST /api/analyze`
Submit repository for analysis

**Request:**
```typescript
interface AnalyzeRequest {
  repoUrl: string;
  projectName?: string;
}

interface AnalyzeResponse {
  projectId: string;
  jobId: string;
  status: 'pending' | 'in_progress' | 'completed' | 'failed';
  message: string;
}

const analyzeRepository = async (
  repoUrl: string,
  projectName?: string
): Promise<AnalyzeResponse> => {
  const response = await apiClient.post('/api/analyze', {
    repo_url: repoUrl,
    project_name: projectName
  });
  return response.data;
};
```

**Example:**
```typescript
const analysis = await analyzeRepository(
  "https://github.com/facebook/react",
  "React Framework"
);
console.log(`Job ID: ${analysis.jobId}`);
console.log(`Project ID: ${analysis.projectId}`);
```

**Response:**
```json
{
  "projectId": "proj_xyz789",
  "jobId": "job_abc123",
  "status": "pending",
  "message": "Analysis job created successfully"
}
```

#### `GET /api/analysis/{job_id}`
Check analysis job status

**Request:**
```typescript
interface JobStatus {
  jobId: string;
  status: 'pending' | 'in_progress' | 'completed' | 'failed';
  progress: number; // 0-100
  currentStep: string;
  result?: AnalysisResult;
  error?: string;
  startedAt: string;
  completedAt?: string;
}

interface AnalysisResult {
  projectId: string;
  scores: Score;
  techStack: TechStack[];
  issues: Issue[];
  insights: string[];
}

const getJobStatus = async (jobId: string): Promise<JobStatus> => {
  const response = await apiClient.get(`/api/analysis/${jobId}`);
  return response.data;
};
```

---

### Leaderboard

#### `GET /api/leaderboard`
Get top-ranked projects

**Request:**
```typescript
interface LeaderboardEntry {
  rank: number;
  projectId: string;
  name: string;
  repoUrl: string;
  totalScore: number;
  algorithmsScore: number;
  llmScore: number;
  qualityScore: number;
  securityScore: number;
  productScore: number;
  language: string;
  stars: number;
  analysisDate: string;
}

const getLeaderboard = async (
  limit: number = 10,
  category?: string
): Promise<LeaderboardEntry[]> => {
  const response = await apiClient.get('/api/leaderboard', {
    params: { limit, category }
  });
  return response.data.leaderboard;
};
```

**Response:**
```json
{
  "leaderboard": [
    {
      "rank": 1,
      "projectId": "proj_abc123",
      "name": "awesome-project",
      "repoUrl": "https://github.com/user/awesome-project",
      "totalScore": 95.5,
      "algorithmsScore": 92,
      "llmScore": 98,
      "qualityScore": 96,
      "securityScore": 94,
      "productScore": 97,
      "language": "Python",
      "stars": 1234,
      "analysisDate": "2026-01-09T10:00:00Z"
    }
  ],
  "total": 42,
  "timestamp": "2026-01-09T10:30:00Z"
}
```

---

## 🎨 Request/Response Examples

### Complete Analysis Flow

```typescript
// 1. Submit repository for analysis
const submitAnalysis = async (repoUrl: string) => {
  try {
    const result = await analyzeRepository(repoUrl);
    console.log('✓ Analysis submitted:', result.jobId);
    return result.jobId;
  } catch (error) {
    console.error('✗ Submission failed:', error);
    throw error;
  }
};

// 2. Poll for job completion
const pollJobStatus = async (jobId: string): Promise<AnalysisResult> => {
  return new Promise((resolve, reject) => {
    const interval = setInterval(async () => {
      try {
        const status = await getJobStatus(jobId);
        
        console.log(`Progress: ${status.progress}% - ${status.currentStep}`);
        
        if (status.status === 'completed' && status.result) {
          clearInterval(interval);
          resolve(status.result);
        } else if (status.status === 'failed') {
          clearInterval(interval);
          reject(new Error(status.error || 'Analysis failed'));
        }
      } catch (error) {
        clearInterval(interval);
        reject(error);
      }
    }, 3000); // Poll every 3 seconds
  });
};

// 3. Use complete flow
const runAnalysis = async (repoUrl: string) => {
  const jobId = await submitAnalysis(repoUrl);
  const result = await pollJobStatus(jobId);
  console.log('✓ Analysis complete:', result);
  return result;
};
```

### Batch Project Fetching

```typescript
const fetchAllProjects = async () => {
  const allProjects: Project[] = [];
  let page = 1;
  const perPage = 50;
  
  while (true) {
    const response = await getProjects(page, perPage);
    allProjects.push(...response.projects);
    
    if (allProjects.length >= response.total) {
      break;
    }
    page++;
  }
  
  return allProjects;
};
```

---

## ⚠️ Error Handling

### Error Response Format

```typescript
interface APIError {
  detail: string;
  status: number;
  timestamp: string;
}
```

### Comprehensive Error Handler

```typescript
import { AxiosError } from 'axios';
import { toast } from 'react-hot-toast'; // or your notification library

export class ApiError extends Error {
  status: number;
  detail: string;
  
  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
    this.detail = detail;
    this.name = 'ApiError';
  }
}

export const handleApiError = (error: unknown): never => {
  if (axios.isAxiosError(error)) {
    const axiosError = error as AxiosError<APIError>;
    
    if (axiosError.response) {
      const { status, data } = axiosError.response;
      const message = data?.detail || axiosError.message;
      
      // Handle specific status codes
      switch (status) {
        case 400:
          toast.error(`Invalid request: ${message}`);
          break;
        case 404:
          toast.error('Resource not found');
          break;
        case 429:
          toast.error('Too many requests. Please try again later');
          break;
        case 500:
          toast.error('Server error. Please try again');
          break;
        default:
          toast.error(message);
      }
      
      throw new ApiError(status, message);
    } else if (axiosError.request) {
      // Network error
      toast.error('Network error. Please check your connection');
      throw new ApiError(0, 'Network error');
    }
  }
  
  // Unknown error
  toast.error('An unexpected error occurred');
  throw error;
};

// Usage
try {
  const result = await analyzeRepository(repoUrl);
} catch (error) {
  handleApiError(error);
}
```

---

## 📘 TypeScript Integration

### Complete Type Definitions

**`types/api.ts`**
```typescript
// Base types
export interface Timestamps {
  createdAt: string;
  updatedAt: string;
}

// Project types
export interface Project extends Timestamps {
  id: number;
  projectId: string;
  name: string;
  description: string | null;
  repoUrl: string;
  language: string | null;
  stars: number | null;
  forks: number | null;
  openIssues: number | null;
  teamSize: number | null;
}

export interface ProjectDetail extends Project {
  techStack: TechStack[];
  issues: Issue[];
  teamMembers: TeamMember[];
  latestScore: Score | null;
}

export interface TechStack {
  id: number;
  technology: string;
  category: 'language' | 'framework' | 'database' | 'tool' | 'other';
  version: string | null;
}

export interface Issue {
  id: number;
  title: string;
  status: 'open' | 'closed' | 'in_progress';
  severity: 'low' | 'medium' | 'high' | 'critical';
  category: string;
  description: string;
  filePath?: string;
  lineNumber?: number;
}

export interface TeamMember {
  id: number;
  name: string;
  email?: string;
  role: string;
  commits: number;
  linesAdded: number;
  linesDeleted: number;
}

export interface Score {
  totalScore: number;
  algorithmsScore: number;
  llmScore: number;
  qualityScore: number;
  securityScore: number;
  productScore: number;
  timestamp: string;
}

// Analysis types
export type JobStatus = 'pending' | 'in_progress' | 'completed' | 'failed';

export interface AnalysisJob {
  jobId: string;
  status: JobStatus;
  progress: number;
  currentStep: string;
  result?: AnalysisResult;
  error?: string;
  startedAt: string;
  completedAt?: string;
}

export interface AnalysisResult {
  projectId: string;
  scores: Score;
  techStack: TechStack[];
  issues: Issue[];
  insights: string[];
}

// Request/Response types
export interface PaginatedResponse<T> {
  data: T[];
  total: number;
  page: number;
  perPage: number;
}

export interface StatsResponse {
  totalProjects: number;
  totalAnalyses: number;
  completedAnalyses: number;
  pendingAnalyses: number;
  failedAnalyses: number;
  avgScore: number;
}
```

### API Service Class

**`services/apiService.ts`**
```typescript
import apiClient from '@/lib/api/client';
import type {
  Project,
  ProjectDetail,
  AnalysisJob,
  LeaderboardEntry,
  StatsResponse,
  PaginatedResponse
} from '@/types/api';

class APIService {
  // Health
  async checkHealth() {
    const { data } = await apiClient.get('/health');
    return data;
  }

  // Stats
  async getStats(): Promise<StatsResponse> {
    const { data } = await apiClient.get('/api/stats');
    return data;
  }

  // Projects
  async getProjects(page = 1, perPage = 10): Promise<PaginatedResponse<Project>> {
    const { data } = await apiClient.get('/api/projects', {
      params: { page, per_page: perPage }
    });
    return data;
  }

  async getProjectById(projectId: string): Promise<ProjectDetail> {
    const { data } = await apiClient.get(`/api/projects/${projectId}`);
    return data;
  }

  async createProject(projectData: {
    name: string;
    repoUrl: string;
    description?: string;
  }): Promise<Project> {
    const { data } = await apiClient.post('/api/projects', {
      name: projectData.name,
      repo_url: projectData.repoUrl,
      description: projectData.description
    });
    return data;
  }

  // Analysis
  async analyzeRepository(repoUrl: string, projectName?: string) {
    const { data } = await apiClient.post('/api/analyze', {
      repo_url: repoUrl,
      project_name: projectName
    });
    return data;
  }

  async getJobStatus(jobId: string): Promise<AnalysisJob> {
    const { data } = await apiClient.get(`/api/analysis/${jobId}`);
    return data;
  }

  // Leaderboard
  async getLeaderboard(limit = 10, category?: string): Promise<LeaderboardEntry[]> {
    const { data } = await apiClient.get('/api/leaderboard', {
      params: { limit, category }
    });
    return data.leaderboard;
  }
}

export const api = new APIService();
export default api;
```

---

## ⚛️ React Integration Examples

### React Query Setup

```typescript
// hooks/useProjects.ts
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '@/services/apiService';

export const useProjects = (page = 1, perPage = 10) => {
  return useQuery({
    queryKey: ['projects', page, perPage],
    queryFn: () => api.getProjects(page, perPage),
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
};

export const useProjectDetails = (projectId: string) => {
  return useQuery({
    queryKey: ['project', projectId],
    queryFn: () => api.getProjectById(projectId),
    enabled: !!projectId,
  });
};

export const useCreateProject = () => {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: api.createProject,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projects'] });
    },
  });
};

// hooks/useAnalysis.ts
export const useAnalyzeRepository = () => {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: ({ repoUrl, projectName }: { repoUrl: string; projectName?: string }) =>
      api.analyzeRepository(repoUrl, projectName),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projects'] });
    },
  });
};

export const useJobStatus = (jobId: string, enabled = true) => {
  return useQuery({
    queryKey: ['job', jobId],
    queryFn: () => api.getJobStatus(jobId),
    enabled: enabled && !!jobId,
    refetchInterval: (data) => {
      // Stop polling when completed or failed
      if (data?.status === 'completed' || data?.status === 'failed') {
        return false;
      }
      return 3000; // Poll every 3 seconds
    },
  });
};
```

### React Component Examples

```typescript
// components/ProjectsList.tsx
import { useProjects } from '@/hooks/useProjects';

export default function ProjectsList() {
  const [page, setPage] = useState(1);
  const { data, isLoading, error } = useProjects(page, 10);

  if (isLoading) return <div>Loading projects...</div>;
  if (error) return <div>Error: {error.message}</div>;

  return (
    <div>
      <h2>Projects ({data.total})</h2>
      {data.projects.map(project => (
        <div key={project.id}>
          <h3>{project.name}</h3>
          <p>{project.description}</p>
          <a href={project.repoUrl}>{project.repoUrl}</a>
        </div>
      ))}
      
      <Pagination
        currentPage={page}
        totalPages={Math.ceil(data.total / 10)}
        onPageChange={setPage}
      />
    </div>
  );
}

// components/AnalyzeRepository.tsx
import { useAnalyzeRepository, useJobStatus } from '@/hooks/useAnalysis';
import { useState } from 'react';

export default function AnalyzeRepository() {
  const [repoUrl, setRepoUrl] = useState('');
  const [jobId, setJobId] = useState<string | null>(null);
  
  const analyzeMutation = useAnalyzeRepository();
  const { data: jobStatus } = useJobStatus(jobId!, !!jobId);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const result = await analyzeMutation.mutateAsync({ repoUrl });
      setJobId(result.jobId);
    } catch (error) {
      console.error('Analysis failed:', error);
    }
  };

  return (
    <div>
      <form onSubmit={handleSubmit}>
        <input
          type="url"
          value={repoUrl}
          onChange={(e) => setRepoUrl(e.target.value)}
          placeholder="https://github.com/user/repo"
          required
        />
        <button type="submit" disabled={analyzeMutation.isPending}>
          {analyzeMutation.isPending ? 'Submitting...' : 'Analyze'}
        </button>
      </form>

      {jobStatus && (
        <div>
          <h3>Analysis Progress</h3>
          <p>Status: {jobStatus.status}</p>
          <p>Progress: {jobStatus.progress}%</p>
          <p>Step: {jobStatus.currentStep}</p>
          
          {jobStatus.status === 'completed' && jobStatus.result && (
            <div>
              <h4>Results</h4>
              <p>Total Score: {jobStatus.result.scores.totalScore}</p>
              <p>Project ID: {jobStatus.result.projectId}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
```

---

## 🔄 WebSocket/Polling for Real-time Updates

### Polling Implementation

```typescript
// hooks/usePolling.ts
import { useEffect, useState } from 'react';

export function usePolling<T>(
  fetchFn: () => Promise<T>,
  interval: number,
  shouldStop: (data: T) => boolean
) {
  const [data, setData] = useState<T | null>(null);
  const [isPolling, setIsPolling] = useState(true);

  useEffect(() => {
    if (!isPolling) return;

    const poll = async () => {
      try {
        const result = await fetchFn();
        setData(result);
        
        if (shouldStop(result)) {
          setIsPolling(false);
        }
      } catch (error) {
        console.error('Polling error:', error);
        setIsPolling(false);
      }
    };

    poll(); // Initial fetch
    const intervalId = setInterval(poll, interval);

    return () => clearInterval(intervalId);
  }, [fetchFn, interval, shouldStop, isPolling]);

  return { data, isPolling, stopPolling: () => setIsPolling(false) };
}

// Usage
const { data: jobStatus } = usePolling(
  () => api.getJobStatus(jobId),
  3000,
  (status) => status.status === 'completed' || status.status === 'failed'
);
```

---

## 🧪 Testing

### Mock API Client

```typescript
// __mocks__/apiClient.ts
import { vi } from 'vitest';

export const mockApiClient = {
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  delete: vi.fn(),
};

export default mockApiClient;
```

### Test Examples

```typescript
// __tests__/apiService.test.ts
import { describe, it, expect, vi } from 'vitest';
import api from '@/services/apiService';
import apiClient from '@/lib/api/client';

vi.mock('@/lib/api/client');

describe('APIService', () => {
  it('should fetch projects', async () => {
    const mockResponse = {
      data: {
        projects: [{ id: 1, name: 'Test Project' }],
        total: 1,
      },
    };
    
    vi.mocked(apiClient.get).mockResolvedValue(mockResponse);
    
    const result = await api.getProjects();
    
    expect(apiClient.get).toHaveBeenCalledWith('/api/projects', {
      params: { page: 1, per_page: 10 }
    });
    expect(result).toEqual(mockResponse.data);
  });
});
```

---

## ✅ Production Checklist

### Pre-deployment

- [ ] Update `NEXT_PUBLIC_API_URL` to production URL
- [ ] Configure CORS on backend for your domain
- [ ] Set up proper error tracking (Sentry, etc.)
- [ ] Implement request retry logic
- [ ] Add request/response logging
- [ ] Set up rate limiting
- [ ] Test all API endpoints
- [ ] Validate TypeScript types

### Security

- [ ] Use HTTPS in production
- [ ] Sanitize user inputs
- [ ] Implement CSRF protection if using cookies
- [ ] Add request timeout handling
- [ ] Validate API responses
- [ ] Don't expose sensitive errors to users

### Performance

- [ ] Implement caching strategy (React Query, SWR)
- [ ] Use pagination for large datasets
- [ ] Optimize bundle size (code splitting)
- [ ] Add loading states
- [ ] Implement optimistic updates
- [ ] Use debouncing for search/filters

### Monitoring

- [ ] Set up API monitoring (Uptime checks)
- [ ] Track API response times
- [ ] Monitor error rates
- [ ] Set up alerts for API downtime
- [ ] Log failed requests

---

## 📞 Support & Resources

- **API Documentation:** http://your-server-ip/docs
- **Backend Repository:** [Your GitHub Repo]
- **Issues:** [GitHub Issues]

---

**Last Updated:** January 9, 2026  
**API Version:** 1.0.0
