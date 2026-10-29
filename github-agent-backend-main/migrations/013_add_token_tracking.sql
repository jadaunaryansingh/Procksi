-- Migration: Add Token Usage Tracking
-- Description: Add columns to track OpenAI API token usage and costs for each analysis

-- Add token usage columns to teams table
DO $$ 
BEGIN
    -- Add prompt tokens column
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'teams' AND column_name = 'openai_prompt_tokens'
    ) THEN
        ALTER TABLE teams ADD COLUMN openai_prompt_tokens INTEGER DEFAULT 0;
        COMMENT ON COLUMN teams.openai_prompt_tokens IS 'Number of input tokens used in OpenAI API call';
    END IF;
    
    -- Add completion tokens column
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'teams' AND column_name = 'openai_completion_tokens'
    ) THEN
        ALTER TABLE teams ADD COLUMN openai_completion_tokens INTEGER DEFAULT 0;
        COMMENT ON COLUMN teams.openai_completion_tokens IS 'Number of output tokens used in OpenAI API call';
    END IF;
    
    -- Add total tokens column
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'teams' AND column_name = 'openai_total_tokens'
    ) THEN
        ALTER TABLE teams ADD COLUMN openai_total_tokens INTEGER DEFAULT 0;
        COMMENT ON COLUMN teams.openai_total_tokens IS 'Total tokens used in OpenAI API call';
    END IF;
    
    -- Add cost column (in USD)
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'teams' AND column_name = 'openai_cost_usd'
    ) THEN
        ALTER TABLE teams ADD COLUMN openai_cost_usd DECIMAL(10, 6) DEFAULT 0.000000;
        COMMENT ON COLUMN teams.openai_cost_usd IS 'Total cost in USD for OpenAI API call';
    END IF;
END $$;

-- Create index for cost tracking queries
CREATE INDEX IF NOT EXISTS idx_teams_openai_cost ON teams(openai_cost_usd);
CREATE INDEX IF NOT EXISTS idx_teams_openai_tokens ON teams(openai_total_tokens);

-- Add token tracking to batch_analysis_runs table
DO $$ 
BEGIN
    -- Add total tokens column
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'batch_analysis_runs' AND column_name = 'total_openai_tokens'
    ) THEN
        ALTER TABLE batch_analysis_runs ADD COLUMN total_openai_tokens INTEGER DEFAULT 0;
        COMMENT ON COLUMN batch_analysis_runs.total_openai_tokens IS 'Total tokens used across all teams in this batch run';
    END IF;
    
    -- Add total cost column
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'batch_analysis_runs' AND column_name = 'total_openai_cost_usd'
    ) THEN
        ALTER TABLE batch_analysis_runs ADD COLUMN total_openai_cost_usd DECIMAL(10, 6) DEFAULT 0.000000;
        COMMENT ON COLUMN batch_analysis_runs.total_openai_cost_usd IS 'Total cost in USD for all OpenAI API calls in this batch run';
    END IF;
END $$;

-- Create index for batch cost tracking
CREATE INDEX IF NOT EXISTS idx_batch_runs_openai_cost ON batch_analysis_runs(total_openai_cost_usd);
