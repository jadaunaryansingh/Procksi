DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_proc
        WHERE proname = 'update_team_student_count'
    ) THEN
        CREATE OR REPLACE FUNCTION update_team_student_count()
        RETURNS TRIGGER AS $$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                IF NEW.team_id IS NOT NULL THEN
                    UPDATE teams
                    SET student_count = (
                        SELECT COUNT(*) FROM students WHERE team_id = NEW.team_id
                    )
                    WHERE id = NEW.team_id;
                END IF;
            ELSIF TG_OP = 'DELETE' THEN
                IF OLD.team_id IS NOT NULL THEN
                    UPDATE teams
                    SET student_count = (
                        SELECT COUNT(*) FROM students WHERE team_id = OLD.team_id
                    )
                    WHERE id = OLD.team_id;
                END IF;
            ELSIF TG_OP = 'UPDATE' THEN
                IF NEW.team_id IS DISTINCT FROM OLD.team_id THEN
                    IF OLD.team_id IS NOT NULL THEN
                        UPDATE teams
                        SET student_count = (
                            SELECT COUNT(*) FROM students WHERE team_id = OLD.team_id
                        )
                        WHERE id = OLD.team_id;
                    END IF;
                    IF NEW.team_id IS NOT NULL THEN
                        UPDATE teams
                        SET student_count = (
                            SELECT COUNT(*) FROM students WHERE team_id = NEW.team_id
                        )
                        WHERE id = NEW.team_id;
                    END IF;
                ELSE
                    IF NEW.team_id IS NOT NULL THEN
                        UPDATE teams
                        SET student_count = (
                            SELECT COUNT(*) FROM students WHERE team_id = NEW.team_id
                        )
                        WHERE id = NEW.team_id;
                    END IF;
                END IF;
            END IF;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_trigger
        WHERE tgname = 'students_update_team_student_count'
    ) THEN
        CREATE TRIGGER students_update_team_student_count
        AFTER INSERT OR UPDATE OR DELETE ON students
        FOR EACH ROW
        EXECUTE FUNCTION update_team_student_count();
    END IF;
END $$;
