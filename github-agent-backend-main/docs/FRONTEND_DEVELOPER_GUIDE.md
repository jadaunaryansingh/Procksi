# Repository Analysis API - Frontend Developer Guide

**Version:** 1.0.0  
**Last Updated:** January 9, 2026  
**Base URL:** `http://localhost:8000` (development)

---

## 📚 Table of Contents

1. [Quick Start](#quick-start)
2. [Authentication](#authentication)
3. [API Endpoints Reference](#api-endpoints-reference)
4. [TypeScript Interfaces](#typescript-interfaces)
5. [Common Use Cases](#common-use-cases)
6. [Error Handling](#error-handling)
7. [Real-Time Updates](#real-time-updates)
8. [Testing & Debugging](#testing--debugging)
9. [Performance Optimization](#performance-optimization)
10. [Production Deployment](#production-deployment)

---

## 🚀 Quick Start

### Installation

```bash
npm install axios
# or
npm install @tanstack/react-query axios
```

### Basic Setup

```typescript
// api/config.ts
export const API_CONFIG = {
  baseURL: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
};

// api/client.ts
import axios from 'axios';
import { API_CONFIG } from './config';

export const apiClient = axios.create(API_CONFIG);

// Add response interceptor for error handling
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    console.error('API Error:', error.response?.data || error.message);
    return Promise.reject(error);
  }
);
```

### First Request

```typescript
import { apiClient } from './api/client';

// Get dashboard statistics
const stats = await apiClient.get('/api/stats');
console.log(stats.data);
// Output: { totalProjects: 10, completedProjects: 8, averageScore: 75.5, ... }
```

---

## 🔐 Authentication

**Current Status:** No authentication required (development)

**Production Ready:** Add JWT token support

```typescript
// Future implementation
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('authToken');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});
```

---

## 📡 API Endpoints Reference

### 1. Submit Repository for Analysis

**Endpoint:** `POST /api/analyze-repo`

**Description:** Submit a GitHub repository for analysis. Returns immediately with job ID for tracking progress.

**Request:**
```typescript
interface AnalyzeRequest {
  repo_url: string;    // Full GitHub URL
  team_name?: string;  // Optional team name
}
```

**Example:**
```typescript
const response = await apiClient.post('/api/analyze-repo', {
  repo_url: 'https://github.com/facebook/react',
  team_name: 'React Team'
});

console.log(response.data);
// {
//   "job_id": "123e4567-e89b-12d3-a456-426614174000",
//   "project_id": "987fcdeb-51a2-43f1-b9e5-ac4c5d6e7890",
//   "message": "Analysis started",
//   "status": "pending"
// }
```

**Status Codes:**
- `200` - Analysis started successfully
- `400` - Invalid repository URL or repository already analyzed
- `500` - Server error

---

### 2. Check Analysis Status

**Endpoint:** `GET /api/analysis-status/{job_id}`

**Description:** Get real-time progress of an analysis job. Poll this endpoint every 2-3 seconds.

**Response:**
```typescript
interface AnalysisStatus {
  job_id: string;
  project_id: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  progress: number;        // 0-100
  current_stage: string;   // See stages below
  message: string;
  error?: string;          // Only present if failed
}
```

**Analysis Stages:**
1. `cloning` - Cloning repository from GitHub
2. `forensic_analysis` - Analyzing commits and contributions
3. `structure_scan` - Scanning project structure
4. `security_check` - Scanning for security issues
5. `ai_detection` - Detecting AI-generated code
6. `quality_analysis` - Analyzing code quality
7. `ai_judge` - AI evaluation in progress
8. `scoring` - Calculating final scores
9. `aggregation` - Finalizing results
10. `completed` - Analysis complete

**Example:**
```typescript
const checkStatus = async (jobId: string): Promise<AnalysisStatus> => {
  const response = await apiClient.get(`/api/analysis-status/${jobId}`);
  return response.data;
};

// Usage
const status = await checkStatus('123e4567-e89b-12d3-a456-426614174000');
console.log(`Progress: ${status.progress}% - ${status.current_stage}`);
```

**Polling Example:**
```typescript
async function waitForCompletion(jobId: string): Promise<string> {
  return new Promise((resolve, reject) => {
    const interval = setInterval(async () => {
      try {
        const status = await checkStatus(jobId);
        
        console.log(`[${status.progress}%] ${status.message}`);
        
        if (status.status === 'completed') {
          clearInterval(interval);
          resolve(status.project_id);
        } else if (status.status === 'failed') {
          clearInterval(interval);
          reject(new Error(status.error || 'Analysis failed'));
        }
      } catch (error) {
        clearInterval(interval);
        reject(error);
      }
    }, 2000); // Poll every 2 seconds
  });
}
```

---

### 3. Get Dashboard Statistics

**Endpoint:** `GET /api/stats`

**Description:** Get aggregate statistics for the dashboard overview.

**Response:**
```typescript
interface DashboardStats {
  totalProjects: number;
  completedProjects: number;
  inProgressProjects: number;
  averageScore: number;
  totalTechnologies: number;
  totalSecurityIssues: number;
  projectsByStatus: {
    completed: number;
    processing: number;
    failed: number;
  };
}
```

**Example:**
```typescript
const stats = await apiClient.get('/api/stats');
console.log(stats.data);
// {
//   "totalProjects": 50,
//   "completedProjects": 45,
//   "inProgressProjects": 3,
//   "averageScore": 72.5,
//   "totalTechnologies": 25,
//   "totalSecurityIssues": 120,
//   "projectsByStatus": {
//     "completed": 45,
//     "processing": 3,
//     "failed": 2
//   }
// }
```

**Use Case:** Display in dashboard hero section or stats cards.

---

### 4. Get All Technologies

**Endpoint:** `GET /api/tech-stacks`

**Description:** Get list of all technologies used across projects with usage count.

**Response:**
```typescript
interface Technology {
  name: string;
  count: number;  // Number of projects using this tech
}

type TechStackResponse = Technology[];
```

**Example:**
```typescript
const techs = await apiClient.get('/api/tech-stacks');
console.log(techs.data);
// [
//   { "name": "Python", "count": 30 },
//   { "name": "JavaScript", "count": 25 },
//   { "name": "React", "count": 20 },
//   { "name": "Docker", "count": 15 }
// ]
```

**Use Case:** Populate filter dropdowns, show popular technologies.

---

### 5. List All Projects

**Endpoint:** `GET /api/projects`

**Description:** Get list of all projects with optional filters. Returns simplified project data for lists/tables.

**Query Parameters:**
- `status` (optional): Filter by status - `all`, `completed`, `processing`, `pending`, `failed`
- `tech` (optional): Filter by technology - e.g., `Python`, `React`
- `sort` (optional): Sort order - `recent` (default), `score`
- `search` (optional): Search in team name or repository URL

**Response:**
```typescript
interface ProjectListItem {
  id: string;
  teamName: string;
  repoUrl: string;
  status: 'completed' | 'processing' | 'pending' | 'failed';
  totalScore: number;
  techStack: string[];        // Top 5 technologies
  securityIssues: number;
  submittedAt: string;        // ISO 8601 format
}

type ProjectListResponse = ProjectListItem[];
```

**Examples:**

```typescript
// Get all completed projects sorted by score
const topProjects = await apiClient.get('/api/projects', {
  params: {
    status: 'completed',
    sort: 'score'
  }
});

// Get Python projects
const pythonProjects = await apiClient.get('/api/projects', {
  params: {
    tech: 'Python'
  }
});

// Search for specific team
const searchResults = await apiClient.get('/api/projects', {
  params: {
    search: 'Team Alpha'
  }
});

// Get recent projects
const recentProjects = await apiClient.get('/api/projects', {
  params: {
    sort: 'recent'
  }
});
```

**Response Example:**
```json
[
  {
    "id": "987fcdeb-51a2-43f1-b9e5-ac4c5d6e7890",
    "teamName": "Team Alpha",
    "repoUrl": "https://github.com/team-alpha/awesome-project",
    "status": "completed",
    "totalScore": 85.5,
    "techStack": ["Python", "FastAPI", "React", "Docker", "PostgreSQL"],
    "securityIssues": 2,
    "submittedAt": "2026-01-08T10:30:00Z"
  }
]
```

**Use Case:** Display in project list, table, or grid view.

---

### 6. Get Project Detail

**Endpoint:** `GET /api/projects/{id}`

**Description:** Get complete evaluation details for a specific project. This is the most data-rich endpoint.

**Response:**
```typescript
interface ProjectEvaluation {
  // Identity
  id: string;
  teamName: string;
  repoUrl: string;
  submittedAt: string;
  status: string;
  
  // Tech Stack
  techStack: string[];
  languages: LanguageBreakdown[];
  architecturePattern: string;
  frameworks: string[];
  
  // Scores (all 0-100)
  totalScore: number;
  qualityScore: number;
  securityScore: number;
  originalityScore: number;
  architectureScore: number;
  documentationScore: number;
  
  // Commit Forensics
  totalCommits: number;
  contributors: ContributorDetail[];
  commitPatterns: CommitPattern[];
  burstCommitWarning: boolean;
  lastMinuteCommits: number;
  
  // Security
  securityIssues: SecurityIssue[];
  secretsDetected: number;
  
  // AI Analysis
  aiGeneratedPercentage: number;
  aiVerdict: string;
  strengths: string[];
  improvements: string[];
  
  // Project Stats
  totalFiles: number;
  totalLinesOfCode: number;
  testCoverage: number;
}

interface LanguageBreakdown {
  name: string;
  percentage: number;
}

interface ContributorDetail {
  name: string;
  commits: number;
  additions: number;
  deletions: number;
  percentage: number;
}

interface CommitPattern {
  pattern: string;
  timeframe: string;
  count: number;
}

interface SecurityIssue {
  type: string;
  severity: 'low' | 'medium' | 'high' | 'critical';
  file: string;
  line?: number;
  description: string;
}
```

**Example:**
```typescript
const projectId = '987fcdeb-51a2-43f1-b9e5-ac4c5d6e7890';
const project = await apiClient.get(`/api/projects/${projectId}`);

console.log(project.data);
// Full ProjectEvaluation object
```

**Response Example:**
```json
{
  "id": "987fcdeb-51a2-43f1-b9e5-ac4c5d6e7890",
  "teamName": "Team Alpha",
  "repoUrl": "https://github.com/team-alpha/awesome-project",
  "submittedAt": "2026-01-08T10:30:00Z",
  "status": "completed",
  
  "techStack": ["Python", "JavaScript", "Docker", "PostgreSQL", "Redis"],
  "languages": [
    { "name": "Python", "percentage": 65.5 },
    { "name": "JavaScript", "percentage": 30.2 },
    { "name": "Shell", "percentage": 4.3 }
  ],
  "architecturePattern": "Microservices",
  "frameworks": ["FastAPI", "React", "Docker"],
  
  "totalScore": 85.5,
  "qualityScore": 90.0,
  "securityScore": 80.0,
  "originalityScore": 85.0,
  "architectureScore": 88.0,
  "documentationScore": 82.0,
  
  "totalCommits": 250,
  "contributors": [
    {
      "name": "John Doe",
      "commits": 150,
      "additions": 5000,
      "deletions": 2000,
      "percentage": 60.0
    },
    {
      "name": "Jane Smith",
      "commits": 100,
      "additions": 3000,
      "deletions": 1000,
      "percentage": 40.0
    }
  ],
  "commitPatterns": [
    {
      "pattern": "Regular development",
      "timeframe": "Last 7 days",
      "count": 45
    }
  ],
  "burstCommitWarning": false,
  "lastMinuteCommits": 3,
  
  "securityIssues": [
    {
      "type": "Hardcoded Secret",
      "severity": "high",
      "file": "config.py",
      "line": 42,
      "description": "API key found in source code"
    }
  ],
  "secretsDetected": 2,
  
  "aiGeneratedPercentage": 15.5,
  "aiVerdict": "The project demonstrates solid engineering practices with clean code structure. Good separation of concerns and consistent coding style throughout.",
  "strengths": [
    "Well-structured codebase with clear separation of concerns",
    "Comprehensive test coverage exceeding 80%",
    "Good documentation with clear README and inline comments",
    "Consistent coding style across the project",
    "Proper error handling implemented"
  ],
  "improvements": [
    "Add more integration tests",
    "Implement rate limiting for API endpoints",
    "Enhance security by using environment variables for secrets",
    "Add CI/CD pipeline configuration",
    "Improve API response time optimization"
  ],
  
  "totalFiles": 156,
  "totalLinesOfCode": 12500,
  "testCoverage": 82.5
}
```

**Use Case:** Display in project detail page with all metrics and analysis.

---

### 7. Get Leaderboard

**Endpoint:** `GET /api/leaderboard`

**Description:** Get ranked list of completed projects. Only includes projects with status `completed`.

**Query Parameters:**
- `tech` (optional): Filter by technology
- `sort` (optional): Score type to sort by - `total`, `quality`, `security`, `originality`, `architecture`, `documentation`
- `search` (optional): Search team names

**Response:**
```typescript
interface LeaderboardEntry {
  id: string;
  teamName: string;
  repoUrl: string;
  techStack: string[];      // Top 5 technologies
  totalScore: number;
  qualityScore: number;
  securityScore: number;
  originalityScore: number;
  architectureScore: number;
  documentationScore: number;
}

type LeaderboardResponse = LeaderboardEntry[];
```

**Examples:**

```typescript
// Get top projects by total score
const leaderboard = await apiClient.get('/api/leaderboard', {
  params: { sort: 'total' }
});

// Get top Python projects
const pythonLeaders = await apiClient.get('/api/leaderboard', {
  params: { 
    tech: 'Python',
    sort: 'total' 
  }
});

// Get top by security score
const secureProjects = await apiClient.get('/api/leaderboard', {
  params: { sort: 'security' }
});

// Search specific team
const teamRanking = await apiClient.get('/api/leaderboard', {
  params: { search: 'Alpha' }
});
```

**Response Example:**
```json
[
  {
    "id": "987fcdeb-51a2-43f1-b9e5-ac4c5d6e7890",
    "teamName": "Team Alpha",
    "repoUrl": "https://github.com/team-alpha/project",
    "techStack": ["Python", "React", "Docker"],
    "totalScore": 95.5,
    "qualityScore": 98.0,
    "securityScore": 92.0,
    "originalityScore": 95.0,
    "architectureScore": 96.0,
    "documentationScore": 94.0
  },
  {
    "id": "123e4567-e89b-12d3-a456-426614174000",
    "teamName": "Team Beta",
    "repoUrl": "https://github.com/team-beta/project",
    "techStack": ["JavaScript", "Node.js", "MongoDB"],
    "totalScore": 88.2,
    "qualityScore": 85.0,
    "securityScore": 90.0,
    "originalityScore": 88.0,
    "architectureScore": 89.0,
    "documentationScore": 87.0
  }
]
```

**Use Case:** Display leaderboard table with rankings.

---

### 8. Get Leaderboard Chart Data

**Endpoint:** `GET /api/leaderboard/chart`

**Description:** Get top 10 projects with all scores for radar/bar chart visualization.

**Response:**
```typescript
interface ChartDataPoint {
  teamName: string;
  totalScore: number;
  qualityScore: number;
  securityScore: number;
  originalityScore: number;
  architectureScore: number;
  documentationScore: number;
}

type ChartDataResponse = ChartDataPoint[];
```

**Example:**
```typescript
const chartData = await apiClient.get('/api/leaderboard/chart');

// Use with Chart.js or Recharts
const labels = chartData.data.map(d => d.teamName);
const scores = chartData.data.map(d => d.totalScore);
```

**Response Example:**
```json
[
  {
    "teamName": "Team Alpha",
    "totalScore": 95.5,
    "qualityScore": 98.0,
    "securityScore": 92.0,
    "originalityScore": 95.0,
    "architectureScore": 96.0,
    "documentationScore": 94.0
  }
]
```

**Use Case:** Render comparison charts (radar, bar, line charts).

---

### 9. Delete Project

**Endpoint:** `DELETE /api/projects/{id}`

**Description:** Delete a project and all associated data (tech stack, issues, team members).

**Response:**
```typescript
interface DeleteResponse {
  message: string;
}
```

**Example:**
```typescript
const projectId = '987fcdeb-51a2-43f1-b9e5-ac4c5d6e7890';
const response = await apiClient.delete(`/api/projects/${projectId}`);

console.log(response.data);
// { "message": "Project deleted successfully" }
```

**Status Codes:**
- `200` - Deleted successfully
- `404` - Project not found
- `500` - Server error

**Use Case:** Admin panel, project management.

---

## 🎯 TypeScript Interfaces

Complete TypeScript definitions for all API responses:

```typescript
// api/types.ts

export interface AnalyzeRequest {
  repo_url: string;
  team_name?: string;
}

export interface AnalyzeResponse {
  job_id: string;
  project_id: string;
  message: string;
  status: 'pending' | 'processing';
}

export type AnalysisStatusType = 'pending' | 'processing' | 'completed' | 'failed';

export interface AnalysisStatus {
  job_id: string;
  project_id: string;
  status: AnalysisStatusType;
  progress: number;
  current_stage: string;
  message: string;
  error?: string;
}

export interface DashboardStats {
  totalProjects: number;
  completedProjects: number;
  inProgressProjects: number;
  averageScore: number;
  totalTechnologies: number;
  totalSecurityIssues: number;
  projectsByStatus: {
    completed: number;
    processing: number;
    failed: number;
  };
}

export interface Technology {
  name: string;
  count: number;
}

export interface ProjectListItem {
  id: string;
  teamName: string;
  repoUrl: string;
  status: 'completed' | 'processing' | 'pending' | 'failed';
  totalScore: number;
  techStack: string[];
  securityIssues: number;
  submittedAt: string;
}

export interface LanguageBreakdown {
  name: string;
  percentage: number;
}

export interface ContributorDetail {
  name: string;
  commits: number;
  additions: number;
  deletions: number;
  percentage: number;
}

export interface CommitPattern {
  pattern: string;
  timeframe: string;
  count: number;
}

export interface SecurityIssue {
  type: string;
  severity: 'low' | 'medium' | 'high' | 'critical';
  file: string;
  line?: number;
  description: string;
}

export interface ProjectEvaluation {
  // Identity
  id: string;
  teamName: string;
  repoUrl: string;
  submittedAt: string;
  status: string;
  
  // Tech Stack
  techStack: string[];
  languages: LanguageBreakdown[];
  architecturePattern: string;
  frameworks: string[];
  
  // Scores
  totalScore: number;
  qualityScore: number;
  securityScore: number;
  originalityScore: number;
  architectureScore: number;
  documentationScore: number;
  
  // Commit Forensics
  totalCommits: number;
  contributors: ContributorDetail[];
  commitPatterns: CommitPattern[];
  burstCommitWarning: boolean;
  lastMinuteCommits: number;
  
  // Security
  securityIssues: SecurityIssue[];
  secretsDetected: number;
  
  // AI Analysis
  aiGeneratedPercentage: number;
  aiVerdict: string;
  strengths: string[];
  improvements: string[];
  
  // Project Stats
  totalFiles: number;
  totalLinesOfCode: number;
  testCoverage: number;
}

export interface LeaderboardEntry {
  id: string;
  teamName: string;
  repoUrl: string;
  techStack: string[];
  totalScore: number;
  qualityScore: number;
  securityScore: number;
  originalityScore: number;
  architectureScore: number;
  documentationScore: number;
}

export interface ChartDataPoint {
  teamName: string;
  totalScore: number;
  qualityScore: number;
  securityScore: number;
  originalityScore: number;
  architectureScore: number;
  documentationScore: number;
}

export interface DeleteResponse {
  message: string;
}

export interface ErrorResponse {
  detail: string;
}
```

---

## 💡 Common Use Cases

### Use Case 1: Submit & Monitor Analysis

Complete flow from submission to displaying results:

```typescript
// services/analysis.service.ts
import { apiClient } from '@/api/client';
import type { AnalyzeRequest, AnalysisStatus, ProjectEvaluation } from '@/api/types';

export class AnalysisService {
  /**
   * Submit a repository for analysis and wait for completion
   */
  static async analyzeRepository(
    repoUrl: string,
    teamName: string,
    onProgress?: (status: AnalysisStatus) => void
  ): Promise<ProjectEvaluation> {
    // Step 1: Submit analysis
    const submitResponse = await apiClient.post<{
      job_id: string;
      project_id: string;
    }>('/api/analyze-repo', {
      repo_url: repoUrl,
      team_name: teamName,
    });

    const { job_id, project_id } = submitResponse.data;

    // Step 2: Poll for status
    const projectId = await this.waitForCompletion(job_id, onProgress);

    // Step 3: Fetch final results
    const resultResponse = await apiClient.get<ProjectEvaluation>(
      `/api/projects/${projectId}`
    );

    return resultResponse.data;
  }

  /**
   * Poll analysis status until completion
   */
  private static async waitForCompletion(
    jobId: string,
    onProgress?: (status: AnalysisStatus) => void
  ): Promise<string> {
    return new Promise((resolve, reject) => {
      const interval = setInterval(async () => {
        try {
          const statusResponse = await apiClient.get<AnalysisStatus>(
            `/api/analysis-status/${jobId}`
          );

          const status = statusResponse.data;
          
          // Call progress callback
          onProgress?.(status);

          if (status.status === 'completed') {
            clearInterval(interval);
            resolve(status.project_id);
          } else if (status.status === 'failed') {
            clearInterval(interval);
            reject(new Error(status.error || 'Analysis failed'));
          }
        } catch (error) {
          clearInterval(interval);
          reject(error);
        }
      }, 2000); // Poll every 2 seconds
    });
  }
}
```

**React Component Example:**

```typescript
// components/AnalyzeForm.tsx
import { useState } from 'react';
import { AnalysisService } from '@/services/analysis.service';
import type { AnalysisStatus } from '@/api/types';

export function AnalyzeForm() {
  const [repoUrl, setRepoUrl] = useState('');
  const [teamName, setTeamName] = useState('');
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [progress, setProgress] = useState<AnalysisStatus | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsAnalyzing(true);

    try {
      const result = await AnalysisService.analyzeRepository(
        repoUrl,
        teamName,
        (status) => {
          setProgress(status);
          console.log(`[${status.progress}%] ${status.message}`);
        }
      );

      console.log('Analysis complete!', result);
      // Redirect to project detail page
      window.location.href = `/projects/${result.id}`;
    } catch (error) {
      console.error('Analysis failed:', error);
      alert('Analysis failed. Please try again.');
    } finally {
      setIsAnalyzing(false);
    }
  };

  return (
    <form onSubmit={handleSubmit}>
      <input
        type="url"
        value={repoUrl}
        onChange={(e) => setRepoUrl(e.target.value)}
        placeholder="https://github.com/username/repo"
        required
      />
      <input
        type="text"
        value={teamName}
        onChange={(e) => setTeamName(e.target.value)}
        placeholder="Team Name (optional)"
      />
      <button type="submit" disabled={isAnalyzing}>
        {isAnalyzing ? 'Analyzing...' : 'Analyze Repository'}
      </button>

      {progress && (
        <div className="progress">
          <div className="progress-bar" style={{ width: `${progress.progress}%` }} />
          <p>{progress.message}</p>
        </div>
      )}
    </form>
  );
}
```

---

### Use Case 2: Display Dashboard

Fetch and display dashboard statistics:

```typescript
// hooks/useDashboard.ts
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '@/api/client';
import type { DashboardStats, ProjectListItem } from '@/api/types';

export function useDashboard() {
  const stats = useQuery({
    queryKey: ['dashboard-stats'],
    queryFn: async () => {
      const response = await apiClient.get<DashboardStats>('/api/stats');
      return response.data;
    },
    refetchInterval: 30000, // Refresh every 30 seconds
  });

  const recentProjects = useQuery({
    queryKey: ['recent-projects'],
    queryFn: async () => {
      const response = await apiClient.get<ProjectListItem[]>('/api/projects', {
        params: { sort: 'recent' }
      });
      return response.data.slice(0, 5); // Top 5
    },
  });

  return {
    stats: stats.data,
    recentProjects: recentProjects.data,
    isLoading: stats.isLoading || recentProjects.isLoading,
  };
}
```

**Component:**

```typescript
// components/Dashboard.tsx
import { useDashboard } from '@/hooks/useDashboard';

export function Dashboard() {
  const { stats, recentProjects, isLoading } = useDashboard();

  if (isLoading) return <div>Loading...</div>;

  return (
    <div className="dashboard">
      <div className="stats-grid">
        <StatCard
          title="Total Projects"
          value={stats?.totalProjects}
          icon="📊"
        />
        <StatCard
          title="Average Score"
          value={`${stats?.averageScore}/100`}
          icon="⭐"
        />
        <StatCard
          title="Technologies"
          value={stats?.totalTechnologies}
          icon="🔧"
        />
        <StatCard
          title="Security Issues"
          value={stats?.totalSecurityIssues}
          icon="🔒"
        />
      </div>

      <div className="recent-projects">
        <h2>Recent Projects</h2>
        {recentProjects?.map((project) => (
          <ProjectCard key={project.id} project={project} />
        ))}
      </div>
    </div>
  );
}
```

---

### Use Case 3: Leaderboard with Filters

```typescript
// hooks/useLeaderboard.ts
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '@/api/client';
import type { LeaderboardEntry } from '@/api/types';

interface LeaderboardFilters {
  tech?: string;
  sort?: 'total' | 'quality' | 'security' | 'originality' | 'architecture' | 'documentation';
  search?: string;
}

export function useLeaderboard(filters: LeaderboardFilters = {}) {
  return useQuery({
    queryKey: ['leaderboard', filters],
    queryFn: async () => {
      const response = await apiClient.get<LeaderboardEntry[]>('/api/leaderboard', {
        params: filters,
      });
      return response.data;
    },
  });
}
```

**Component:**

```typescript
// components/Leaderboard.tsx
import { useState } from 'react';
import { useLeaderboard } from '@/hooks/useLeaderboard';

export function Leaderboard() {
  const [tech, setTech] = useState<string>('');
  const [sort, setSort] = useState<string>('total');
  const [search, setSearch] = useState<string>('');

  const { data: leaderboard, isLoading } = useLeaderboard({
    tech: tech || undefined,
    sort: sort as any,
    search: search || undefined,
  });

  return (
    <div className="leaderboard">
      <div className="filters">
        <select value={tech} onChange={(e) => setTech(e.target.value)}>
          <option value="">All Technologies</option>
          <option value="Python">Python</option>
          <option value="JavaScript">JavaScript</option>
          <option value="React">React</option>
        </select>

        <select value={sort} onChange={(e) => setSort(e.target.value)}>
          <option value="total">Total Score</option>
          <option value="quality">Quality</option>
          <option value="security">Security</option>
          <option value="originality">Originality</option>
        </select>

        <input
          type="search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search teams..."
        />
      </div>

      {isLoading ? (
        <div>Loading...</div>
      ) : (
        <table className="leaderboard-table">
          <thead>
            <tr>
              <th>Rank</th>
              <th>Team</th>
              <th>Tech Stack</th>
              <th>Total Score</th>
              <th>Quality</th>
              <th>Security</th>
            </tr>
          </thead>
          <tbody>
            {leaderboard?.map((entry, index) => (
              <tr key={entry.id}>
                <td>{index + 1}</td>
                <td>{entry.teamName}</td>
                <td>{entry.techStack.join(', ')}</td>
                <td>{entry.totalScore}</td>
                <td>{entry.qualityScore}</td>
                <td>{entry.securityScore}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
```

---

### Use Case 4: Project Detail Page

```typescript
// hooks/useProject.ts
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '@/api/client';
import type { ProjectEvaluation } from '@/api/types';

export function useProject(projectId: string) {
  return useQuery({
    queryKey: ['project', projectId],
    queryFn: async () => {
      const response = await apiClient.get<ProjectEvaluation>(
        `/api/projects/${projectId}`
      );
      return response.data;
    },
    enabled: !!projectId,
  });
}
```

**Component:**

```typescript
// pages/ProjectDetailPage.tsx
import { useParams } from 'react-router-dom';
import { useProject } from '@/hooks/useProject';
import { ScoreGauge } from '@/components/ScoreGauge';
import { ContributorsList } from '@/components/ContributorsList';
import { SecurityIssues } from '@/components/SecurityIssues';

export function ProjectDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { data: project, isLoading } = useProject(id!);

  if (isLoading) return <div>Loading...</div>;
  if (!project) return <div>Project not found</div>;

  return (
    <div className="project-detail">
      <header>
        <h1>{project.teamName}</h1>
        <a href={project.repoUrl} target="_blank" rel="noopener">
          View on GitHub
        </a>
      </header>

      <section className="scores">
        <ScoreGauge label="Total" score={project.totalScore} />
        <ScoreGauge label="Quality" score={project.qualityScore} />
        <ScoreGauge label="Security" score={project.securityScore} />
        <ScoreGauge label="Originality" score={project.originalityScore} />
        <ScoreGauge label="Architecture" score={project.architectureScore} />
        <ScoreGauge label="Documentation" score={project.documentationScore} />
      </section>

      <section className="tech-stack">
        <h2>Tech Stack</h2>
        <div className="tags">
          {project.techStack.map((tech) => (
            <span key={tech} className="tag">{tech}</span>
          ))}
        </div>

        <h3>Languages</h3>
        {project.languages.map((lang) => (
          <div key={lang.name} className="language">
            <span>{lang.name}</span>
            <div className="bar" style={{ width: `${lang.percentage}%` }} />
            <span>{lang.percentage}%</span>
          </div>
        ))}
      </section>

      <section className="contributors">
        <h2>Contributors ({project.contributors.length})</h2>
        <ContributorsList contributors={project.contributors} />
      </section>

      <section className="security">
        <h2>Security Analysis</h2>
        <p>Secrets Detected: {project.secretsDetected}</p>
        <SecurityIssues issues={project.securityIssues} />
      </section>

      <section className="ai-analysis">
        <h2>AI Analysis</h2>
        <p>AI Generated: {project.aiGeneratedPercentage}%</p>
        <div className="verdict">{project.aiVerdict}</div>

        <h3>Strengths</h3>
        <ul>
          {project.strengths.map((strength, i) => (
            <li key={i}>{strength}</li>
          ))}
        </ul>

        <h3>Areas for Improvement</h3>
        <ul>
          {project.improvements.map((improvement, i) => (
            <li key={i}>{improvement}</li>
          ))}
        </ul>
      </section>

      <section className="stats">
        <h2>Project Statistics</h2>
        <div className="stat">
          <span>Total Files:</span>
          <strong>{project.totalFiles}</strong>
        </div>
        <div className="stat">
          <span>Lines of Code:</span>
          <strong>{project.totalLinesOfCode.toLocaleString()}</strong>
        </div>
        <div className="stat">
          <span>Test Coverage:</span>
          <strong>{project.testCoverage}%</strong>
        </div>
      </section>
    </div>
  );
}
```

---

## ⚠️ Error Handling

### Standard Error Response

All errors follow this format:

```typescript
interface ErrorResponse {
  detail: string;  // Human-readable error message
}
```

### HTTP Status Codes

- `200` - Success
- `400` - Bad Request (invalid input, duplicate submission)
- `404` - Not Found (project doesn't exist)
- `500` - Internal Server Error
- `503` - Service Unavailable (database error)

### Error Handling Implementation

```typescript
// api/client.ts
import axios from 'axios';
import type { ErrorResponse } from './types';

export const apiClient = axios.create({
  baseURL: 'http://localhost:8000',
  timeout: 30000,
});

// Response interceptor for error handling
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response) {
      // Server responded with error
      const errorData = error.response.data as ErrorResponse;
      
      switch (error.response.status) {
        case 400:
          console.error('Bad Request:', errorData.detail);
          throw new Error(errorData.detail);
        
        case 404:
          console.error('Not Found:', errorData.detail);
          throw new Error('Resource not found');
        
        case 500:
          console.error('Server Error:', errorData.detail);
          throw new Error('Server error. Please try again later.');
        
        case 503:
          console.error('Service Unavailable:', errorData.detail);
          throw new Error('Service temporarily unavailable');
        
        default:
          throw new Error(errorData.detail || 'An error occurred');
      }
    } else if (error.request) {
      // Request made but no response
      console.error('Network Error:', error.message);
      throw new Error('Network error. Please check your connection.');
    } else {
      // Something else happened
      console.error('Error:', error.message);
      throw error;
    }
  }
);
```

**React Error Boundary:**

```typescript
// components/ErrorBoundary.tsx
import { Component, ReactNode } from 'react';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: any) {
    console.error('Error caught by boundary:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="error-page">
          <h1>Something went wrong</h1>
          <p>{this.state.error?.message}</p>
          <button onClick={() => window.location.reload()}>
            Reload Page
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
```

---

## 🔄 Real-Time Updates

### WebSocket Alternative: Polling Pattern

Since WebSocket isn't currently implemented, use smart polling:

```typescript
// hooks/useAnalysisPolling.ts
import { useEffect, useState } from 'react';
import { apiClient } from '@/api/client';
import type { AnalysisStatus } from '@/api/types';

export function useAnalysisPolling(jobId: string | null) {
  const [status, setStatus] = useState<AnalysisStatus | null>(null);
  const [isPolling, setIsPolling] = useState(false);

  useEffect(() => {
    if (!jobId) return;

    setIsPolling(true);
    let interval: NodeJS.Timeout;

    const poll = async () => {
      try {
        const response = await apiClient.get<AnalysisStatus>(
          `/api/analysis-status/${jobId}`
        );
        
        setStatus(response.data);

        // Stop polling if completed or failed
        if (['completed', 'failed'].includes(response.data.status)) {
          clearInterval(interval);
          setIsPolling(false);
        }
      } catch (error) {
        console.error('Polling error:', error);
        clearInterval(interval);
        setIsPolling(false);
      }
    };

    // Initial poll
    poll();

    // Poll every 2 seconds
    interval = setInterval(poll, 2000);

    return () => {
      if (interval) clearInterval(interval);
    };
  }, [jobId]);

  return { status, isPolling };
}
```

### Smart Polling with Exponential Backoff

For long-running analyses:

```typescript
class SmartPoller {
  private interval: number = 2000; // Start with 2 seconds
  private maxInterval: number = 30000; // Max 30 seconds
  private multiplier: number = 1.5;

  async poll<T>(
    fetchFn: () => Promise<T>,
    shouldContinue: (data: T) => boolean,
    onUpdate: (data: T) => void
  ): Promise<T> {
    let data = await fetchFn();
    onUpdate(data);

    while (shouldContinue(data)) {
      await new Promise((resolve) => setTimeout(resolve, this.interval));
      
      data = await fetchFn();
      onUpdate(data);

      // Increase interval (exponential backoff)
      this.interval = Math.min(
        this.interval * this.multiplier,
        this.maxInterval
      );
    }

    return data;
  }
}

// Usage
const poller = new SmartPoller();

const finalStatus = await poller.poll(
  () => apiClient.get(`/api/analysis-status/${jobId}`).then(r => r.data),
  (status) => !['completed', 'failed'].includes(status.status),
  (status) => console.log(`Progress: ${status.progress}%`)
);
```

---

## 🧪 Testing & Debugging

### Manual Testing with cURL

```bash
# Submit analysis
curl -X POST http://localhost:8000/api/analyze-repo \
  -H "Content-Type: application/json" \
  -d '{"repo_url": "https://github.com/facebook/react", "team_name": "React Team"}'

# Check status
curl http://localhost:8000/api/analysis-status/JOB_ID

# Get dashboard stats
curl http://localhost:8000/api/stats

# Get projects list
curl "http://localhost:8000/api/projects?sort=score&status=completed"

# Get project detail
curl http://localhost:8000/api/projects/PROJECT_ID

# Get leaderboard
curl "http://localhost:8000/api/leaderboard?sort=total"
```

### Testing with Postman/Insomnia

Import this collection:

```json
{
  "name": "Repository Analysis API",
  "requests": [
    {
      "name": "Submit Analysis",
      "method": "POST",
      "url": "{{baseUrl}}/api/analyze-repo",
      "body": {
        "repo_url": "https://github.com/username/repo",
        "team_name": "My Team"
      }
    },
    {
      "name": "Check Status",
      "method": "GET",
      "url": "{{baseUrl}}/api/analysis-status/{{jobId}}"
    },
    {
      "name": "Get Dashboard Stats",
      "method": "GET",
      "url": "{{baseUrl}}/api/stats"
    }
  ]
}
```

### Interactive API Documentation

Visit these URLs when the server is running:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Browser DevTools

Monitor API calls in browser console:

```typescript
// Add to your app initialization
if (process.env.NODE_ENV === 'development') {
  apiClient.interceptors.request.use((config) => {
    console.log('→ API Request:', config.method?.toUpperCase(), config.url, config.params);
    return config;
  });

  apiClient.interceptors.response.use((response) => {
    console.log('← API Response:', response.config.url, response.status, response.data);
    return response;
  });
}
```

---

## ⚡ Performance Optimization

### 1. Caching with React Query

```typescript
// config/queryClient.ts
import { QueryClient } from '@tanstack/react-query';

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000, // 5 minutes
      cacheTime: 10 * 60 * 1000, // 10 minutes
      refetchOnWindowFocus: false,
      retry: 2,
    },
  },
});
```

### 2. Prefetching Data

```typescript
// Prefetch project detail before navigating
const handleProjectClick = (projectId: string) => {
  // Prefetch in background
  queryClient.prefetchQuery({
    queryKey: ['project', projectId],
    queryFn: () => apiClient.get(`/api/projects/${projectId}`).then(r => r.data),
  });

  // Navigate
  router.push(`/projects/${projectId}`);
};
```

### 3. Debounced Search

```typescript
import { useMemo } from 'react';
import { debounce } from 'lodash';

function SearchableProjectList() {
  const [search, setSearch] = useState('');

  const debouncedSearch = useMemo(
    () => debounce((value: string) => {
      // Trigger search
      refetch({ search: value });
    }, 500),
    []
  );

  return (
    <input
      type="search"
      onChange={(e) => {
        setSearch(e.target.value);
        debouncedSearch(e.target.value);
      }}
    />
  );
}
```

### 4. Pagination (Future Enhancement)

```typescript
// When pagination is added to the API
function useProjects(page: number = 1, pageSize: number = 20) {
  return useQuery({
    queryKey: ['projects', page, pageSize],
    queryFn: async () => {
      const response = await apiClient.get('/api/projects', {
        params: { page, page_size: pageSize }
      });
      return response.data;
    },
  });
}
```

---

## 🚀 Production Deployment

### Environment Variables

```env
# .env.production
NEXT_PUBLIC_API_URL=https://api.yourproject.com
NEXT_PUBLIC_API_TIMEOUT=30000
NEXT_PUBLIC_ENABLE_ANALYTICS=true
```

### API Client Configuration

```typescript
// api/config.ts
const config = {
  development: {
    baseURL: 'http://localhost:8000',
    timeout: 30000,
  },
  production: {
    baseURL: process.env.NEXT_PUBLIC_API_URL,
    timeout: 30000,
  },
};

export const apiConfig = config[process.env.NODE_ENV as 'development' | 'production'];
```

### CORS Configuration

Ensure backend allows your frontend origin:

```python
# Backend CORS settings (already configured)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://yourfrontend.com"],  # Update in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Health Check Monitoring

```typescript
// utils/healthCheck.ts
export async function checkApiHealth(): Promise<boolean> {
  try {
    const response = await apiClient.get('/health');
    return response.data.status === 'healthy';
  } catch (error) {
    console.error('API health check failed:', error);
    return false;
  }
}

// Run on app initialization
checkApiHealth().then((isHealthy) => {
  if (!isHealthy) {
    console.error('API is not healthy!');
    // Show maintenance page or notification
  }
});
```

### Error Tracking

```typescript
// Integrate with Sentry
import * as Sentry from '@sentry/react';

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    Sentry.captureException(error);
    throw error;
  }
);
```

---

## 📞 Support & Troubleshooting

### Common Issues

**1. CORS Errors**
```
Access to XMLHttpRequest blocked by CORS policy
```
**Solution:** Ensure backend CORS middleware is configured correctly. In development, use proxy or allow `http://localhost:3000`.

**2. Network Timeout**
```
timeout of 30000ms exceeded
```
**Solution:** Analysis can take time. Increase timeout or implement proper progress monitoring.

**3. 404 Not Found**
```
GET /api/projects/undefined 404
```
**Solution:** Ensure project ID is valid before making request. Add proper error handling.

**4. 400 Repository Already Analyzed**
```
{"detail": "Repository already completed"}
```
**Solution:** Check if repository was previously analyzed. Fetch existing results instead.

### Debug Mode

Enable debug logging:

```typescript
// Add to app initialization
if (process.env.NODE_ENV === 'development') {
  window.API_DEBUG = true;
  
  apiClient.interceptors.request.use((config) => {
    console.group(`📤 ${config.method?.toUpperCase()} ${config.url}`);
    console.log('Params:', config.params);
    console.log('Body:', config.data);
    console.groupEnd();
    return config;
  });

  apiClient.interceptors.response.use((response) => {
    console.group(`📥 ${response.config.url} - ${response.status}`);
    console.log('Data:', response.data);
    console.groupEnd();
    return response;
  });
}
```

### Getting Help

1. Check server logs: `python main.py`
2. Visit interactive docs: http://localhost:8000/docs
3. Test with cURL to isolate frontend issues
4. Check browser network tab for actual requests/responses

---

## 🎓 Best Practices

1. **Always handle loading states** - API calls can take time
2. **Implement error boundaries** - Gracefully handle failures
3. **Cache aggressively** - Use React Query's caching
4. **Show progress feedback** - Especially for analysis submission
5. **Validate input** - Check URLs before submission
6. **Use TypeScript** - Leverage type safety
7. **Monitor performance** - Track API response times
8. **Handle edge cases** - Empty lists, missing data, etc.

---

## 📝 Changelog

### Version 1.0.0 (January 9, 2026)
- Initial API release
- 7 core endpoints
- Complete camelCase response format
- Dashboard statistics
- Leaderboard with filters
- Project detail view
- Real-time progress tracking

---

## 📧 Contact

**API Issues:** Check server logs and `/docs` endpoint  
**Questions:** Review this guide and interactive documentation

---

**Happy Coding! 🚀**
