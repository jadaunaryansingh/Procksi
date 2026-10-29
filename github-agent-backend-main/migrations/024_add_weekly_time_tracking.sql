-- Migration: Add weekly time tracking columns
-- This allows tracking cumulative time spent during the current week

-- Add columns for weekly time tracking
ALTER TABLE public.users
ADD COLUMN IF NOT EXISTS weekly_time_spent INTERVAL DEFAULT INTERVAL '0 seconds',
ADD COLUMN IF NOT EXISTS week_start_date DATE;

-- Update existing users to set week_start_date to current week's Sunday
UPDATE public.users
SET week_start_date = CURRENT_DATE - (EXTRACT(DOW FROM CURRENT_DATE)::INTEGER)
WHERE week_start_date IS NULL;

-- Function to update weekly time on logout
CREATE OR REPLACE FUNCTION update_weekly_time_on_logout()
RETURNS TRIGGER AS $$
DECLARE
    current_week_start DATE;
    session_duration INTERVAL;
BEGIN
    -- Calculate current week's Sunday
    current_week_start := CURRENT_DATE - (EXTRACT(DOW FROM CURRENT_DATE)::INTEGER);
    
    -- Check if we need to reset weekly time (new week started)
    IF NEW.week_start_date IS NULL OR NEW.week_start_date < current_week_start THEN
        -- New week, reset weekly time
        NEW.weekly_time_spent := INTERVAL '0 seconds';
        NEW.week_start_date := current_week_start;
    END IF;
    
    -- If user is being set to offline and has a last_login
    IF NEW.is_online = false AND OLD.is_online = true AND NEW.last_login IS NOT NULL AND NEW.last_logout IS NOT NULL THEN
        -- Calculate session duration
        session_duration := NEW.last_logout - NEW.last_login;
        
        -- Add session duration to weekly time if session was in current week
        IF NEW.last_login::DATE >= current_week_start THEN
            -- Initialize weekly_time_spent if NULL
            IF NEW.weekly_time_spent IS NULL THEN
                NEW.weekly_time_spent := INTERVAL '0 seconds';
            END IF;
            
            -- Add session duration
            NEW.weekly_time_spent := NEW.weekly_time_spent + session_duration;
        END IF;
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger to update weekly time on logout
DROP TRIGGER IF EXISTS update_weekly_time_trigger ON public.users;
CREATE TRIGGER update_weekly_time_trigger
    BEFORE UPDATE ON public.users
    FOR EACH ROW
    WHEN (NEW.is_online = false AND OLD.is_online = true)
    EXECUTE FUNCTION update_weekly_time_on_logout();

-- Function to reset weekly time for all users (should be called weekly via cron)
CREATE OR REPLACE FUNCTION reset_weekly_time_for_new_week()
RETURNS void AS $$
DECLARE
    current_week_start DATE;
BEGIN
    current_week_start := CURRENT_DATE - (EXTRACT(DOW FROM CURRENT_DATE)::INTEGER);
    
    -- Reset weekly time for users whose week_start_date is before current week
    UPDATE public.users
    SET 
        weekly_time_spent = INTERVAL '0 seconds',
        week_start_date = current_week_start
    WHERE week_start_date < current_week_start;
    
    RAISE NOTICE 'Reset weekly time for new week starting %', current_week_start;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Add comments
COMMENT ON COLUMN public.users.weekly_time_spent IS 'Cumulative time spent during the current calendar week (Sunday to Saturday)';
COMMENT ON COLUMN public.users.week_start_date IS 'Start date of the current tracking week (Sunday)';
COMMENT ON FUNCTION update_weekly_time_on_logout() IS 'Automatically updates weekly_time_spent when user logs out';
COMMENT ON FUNCTION reset_weekly_time_for_new_week() IS 'Resets weekly time for all users at the start of a new week. Should be called by a cron job every Sunday.';
