DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_proc
        WHERE proname = 'update_batch_team_count'
    ) THEN
        CREATE OR REPLACE FUNCTION update_batch_team_count()
        RETURNS TRIGGER AS $func$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                IF NEW.batch_id IS NOT NULL THEN
                    UPDATE batches
                    SET team_count = (
                        SELECT COUNT(*) FROM teams WHERE batch_id = NEW.batch_id
                    )
                    WHERE id = NEW.batch_id;
                END IF;
            ELSIF TG_OP = 'DELETE' THEN
                IF OLD.batch_id IS NOT NULL THEN
                    UPDATE batches
                    SET team_count = (
                        SELECT COUNT(*) FROM teams WHERE batch_id = OLD.batch_id
                    )
                    WHERE id = OLD.batch_id;
                END IF;
            ELSIF TG_OP = 'UPDATE' THEN
                IF NEW.batch_id IS DISTINCT FROM OLD.batch_id THEN
                    IF OLD.batch_id IS NOT NULL THEN
                        UPDATE batches
                        SET team_count = (
                            SELECT COUNT(*) FROM teams WHERE batch_id = OLD.batch_id
                        )
                        WHERE id = OLD.batch_id;
                    END IF;
                    IF NEW.batch_id IS NOT NULL THEN
                        UPDATE batches
                        SET team_count = (
                            SELECT COUNT(*) FROM teams WHERE batch_id = NEW.batch_id
                        )
                        WHERE id = NEW.batch_id;
                    END IF;
                ELSE
                    IF NEW.batch_id IS NOT NULL THEN
                        UPDATE batches
                        SET team_count = (
                            SELECT COUNT(*) FROM teams WHERE batch_id = NEW.batch_id
                        )
                        WHERE id = NEW.batch_id;
                    END IF;
                END IF;
            END IF;
            RETURN NULL;
        END;
        $func$ LANGUAGE plpgsql;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_trigger
        WHERE tgname = 'teams_update_batch_team_count'
    ) THEN
        CREATE TRIGGER teams_update_batch_team_count
        AFTER INSERT OR UPDATE OR DELETE ON teams
        FOR EACH ROW
        EXECUTE FUNCTION update_batch_team_count();
    END IF;
END $$;
