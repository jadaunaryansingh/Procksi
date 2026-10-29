-- Migration: Add trigger to track auth.users login activity
-- This trigger automatically updates the users table when Supabase auth occurs
-- NO FRONTEND CHANGES REQUIRED - works with direct Supabase authentication

-- Function to sync auth activity to users table
CREATE OR REPLACE FUNCTION sync_auth_activity()
RETURNS TRIGGER AS $$
BEGIN
  -- On user login (last_sign_in_at updated)
  IF (TG_OP = 'UPDATE' AND NEW.last_sign_in_at IS DISTINCT FROM OLD.last_sign_in_at) THEN
    -- User just logged in
    UPDATE public.users
    SET 
      last_login = NEW.last_sign_in_at,
      is_online = true,
      updated_at = NOW()
    WHERE id = NEW.id;
    
    RAISE NOTICE 'User % logged in at %', NEW.id, NEW.last_sign_in_at;
  END IF;
  
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Create trigger on auth.users table
DROP TRIGGER IF EXISTS on_auth_user_login ON auth.users;
CREATE TRIGGER on_auth_user_login
  AFTER UPDATE ON auth.users
  FOR EACH ROW
  EXECUTE FUNCTION sync_auth_activity();

-- Function to handle logout tracking via heartbeat timeout
-- This function should be called periodically (e.g., every 5 minutes) to mark inactive users as offline
CREATE OR REPLACE FUNCTION mark_inactive_users_offline()
RETURNS void AS $$
BEGIN
  -- Mark users as offline if they haven't been active for 10 minutes
  UPDATE public.users
  SET 
    is_online = false,
    last_logout = NOW(),
    total_time_spent = COALESCE(total_time_spent, INTERVAL '0 seconds') + 
                       (NOW() - COALESCE(last_login, NOW()))
  WHERE is_online = true
    AND last_login IS NOT NULL
    AND last_login < NOW() - INTERVAL '10 minutes';
    
  RAISE NOTICE 'Marked inactive users as offline';
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Add comments
COMMENT ON FUNCTION sync_auth_activity() IS 'Automatically syncs auth.users login activity to public.users table';
COMMENT ON FUNCTION mark_inactive_users_offline() IS 'Marks users as offline after 10 minutes of inactivity. Should be called periodically by a cron job or scheduler.';
