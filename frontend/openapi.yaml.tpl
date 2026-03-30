openapi: 3.0.3
info:
  title: Memoire API
  description: |
    Personal productivity API for tasks, notes, habits, journal, health, nutrition, and goals.

    All endpoints require a valid JWT in the `Authorization: Bearer <token>` header.
    Tokens are issued by Cognito (or your configured OIDC provider).
  version: "1.0.0"

servers:
  - url: ${api_url}
    description: Deployed API

security:
  - bearerAuth: []

components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT

  schemas:
    Error:
      type: object
      properties:
        error:
          type: string
      required: [error]

    # ── Journal ────────────────────────────────────────────────────────────────

    JournalEntry:
      type: object
      properties:
        user_id:
          type: string
        entry_date:
          type: string
          format: date
          example: "2024-03-15"
        title:
          type: string
          example: "A good day"
        body:
          type: string
          description: Markdown content
        mood:
          type: string
          enum: [great, good, okay, bad, terrible]
        tags:
          type: array
          items:
            type: string
        created_at:
          type: string
          format: date-time
        updated_at:
          type: string
          format: date-time

    JournalSummary:
      type: object
      description: Returned by list/search — body is truncated to 200 chars
      properties:
        user_id:
          type: string
        entry_date:
          type: string
          format: date
        title:
          type: string
        body:
          type: string
          description: First 200 characters of body
        mood:
          type: string
          enum: [great, good, okay, bad, terrible]
        tags:
          type: array
          items:
            type: string
        created_at:
          type: string
          format: date-time
        updated_at:
          type: string
          format: date-time

    JournalWrite:
      type: object
      properties:
        title:
          type: string
        body:
          type: string
        mood:
          type: string
          enum: [great, good, okay, bad, terrible]
        tags:
          type: array
          items:
            type: string

    # ── Goals ─────────────────────────────────────────────────────────────────

    Goal:
      type: object
      properties:
        user_id:
          type: string
        goal_id:
          type: string
          format: uuid
        title:
          type: string
        description:
          type: string
        target_date:
          type: string
          format: date
          nullable: true
        status:
          type: string
          enum: [active, completed, abandoned]
        created_at:
          type: string
          format: date-time
        updated_at:
          type: string
          format: date-time

    GoalWrite:
      type: object
      required: [title]
      properties:
        title:
          type: string
        description:
          type: string
        target_date:
          type: string
          format: date
          nullable: true
        status:
          type: string
          enum: [active, completed, abandoned]

    # ── Tasks ─────────────────────────────────────────────────────────────────

    TaskNotifications:
      type: object
      properties:
        before_due:
          type: array
          items:
            type: string
            enum: ["1h", "1d", "3d"]
          description: Send ntfy alert this far before due date
        recurring:
          type: string
          enum: ["1h", "1d", "1w"]
          nullable: true
          description: Recurring reminder interval

    Task:
      type: object
      properties:
        user_id:
          type: string
        task_id:
          type: string
          format: uuid
        title:
          type: string
        description:
          type: string
        status:
          type: string
          enum: [todo, in_progress, done]
        priority:
          type: string
          enum: [low, medium, high]
        due_date:
          type: string
          format: date
          nullable: true
        folder_id:
          type: string
          format: uuid
          nullable: true
        notifications:
          $ref: '#/components/schemas/TaskNotifications'
        created_at:
          type: string
          format: date-time
        updated_at:
          type: string
          format: date-time

    TaskWrite:
      type: object
      required: [title]
      properties:
        title:
          type: string
        description:
          type: string
        status:
          type: string
          enum: [todo, in_progress, done]
        priority:
          type: string
          enum: [low, medium, high]
        due_date:
          type: string
          format: date
          nullable: true
        folder_id:
          type: string
          format: uuid
          nullable: true
        notifications:
          $ref: '#/components/schemas/TaskNotifications'

    TaskFolder:
      type: object
      properties:
        user_id:
          type: string
        folder_id:
          type: string
          format: uuid
        name:
          type: string
        parent_id:
          type: string
          format: uuid
          nullable: true

    TaskFolderWrite:
      type: object
      required: [name]
      properties:
        name:
          type: string
        parent_id:
          type: string
          format: uuid
          nullable: true

    # ── Notes ─────────────────────────────────────────────────────────────────

    Note:
      type: object
      properties:
        user_id:
          type: string
        note_id:
          type: string
          format: uuid
        folder_id:
          type: string
          format: uuid
        title:
          type: string
        body:
          type: string
          description: Markdown content
        tags:
          type: array
          items:
            type: string
        created_at:
          type: string
          format: date-time
        updated_at:
          type: string
          format: date-time

    NoteSummary:
      type: object
      description: Returned by list/search — body is truncated to 200 chars
      properties:
        user_id:
          type: string
        note_id:
          type: string
          format: uuid
        folder_id:
          type: string
          format: uuid
        title:
          type: string
        body:
          type: string
          description: First 200 characters of body
        tags:
          type: array
          items:
            type: string
        created_at:
          type: string
          format: date-time
        updated_at:
          type: string
          format: date-time

    NoteWrite:
      type: object
      required: [folder_id]
      properties:
        folder_id:
          type: string
          format: uuid
        title:
          type: string
        body:
          type: string
        tags:
          type: array
          items:
            type: string

    NoteFolder:
      type: object
      properties:
        user_id:
          type: string
        folder_id:
          type: string
          format: uuid
        name:
          type: string
        parent_id:
          type: string
          format: uuid
          nullable: true

    NoteFolderWrite:
      type: object
      required: [name]
      properties:
        name:
          type: string
        parent_id:
          type: string
          format: uuid
          nullable: true

    NoteAttachment:
      type: object
      properties:
        attachment_id:
          type: string
          format: uuid
        note_id:
          type: string
          format: uuid
        filename:
          type: string
        content_type:
          type: string
        size_bytes:
          type: integer
        download_url:
          type: string
        created_at:
          type: string
          format: date-time

    PresignedUpload:
      type: object
      properties:
        upload_url:
          type: string
          description: Presigned S3 PUT URL
        key:
          type: string
          description: S3 object key — pass as `?key=` when retrieving

    # ── Habits ────────────────────────────────────────────────────────────────

    HabitHistory:
      type: object
      properties:
        date:
          type: string
          format: date
        done:
          type: boolean

    Habit:
      type: object
      properties:
        user_id:
          type: string
        habit_id:
          type: string
          format: uuid
        name:
          type: string
        notify_time:
          type: string
          example: "08:00"
          description: UTC time in HH:MM (24h) for daily ntfy reminder; empty string disables
          nullable: true
        created_at:
          type: string
          format: date
        history:
          type: array
          items:
            $ref: '#/components/schemas/HabitHistory'
          description: Rolling 30-day completion history
        done_today:
          type: boolean
        current_streak:
          type: integer
          description: Consecutive days completed up to today
        best_streak:
          type: integer
          description: Longest consecutive run within the 30-day window

    HabitWrite:
      type: object
      required: [name]
      properties:
        name:
          type: string
        notify_time:
          type: string
          example: "08:00"
          nullable: true

    # ── Health ────────────────────────────────────────────────────────────────

    ExerciseSet:
      type: object
      properties:
        reps:
          type: integer
          nullable: true
        weight:
          type: number
          nullable: true

    Exercise:
      type: object
      properties:
        id:
          type: string
          format: uuid
          description: Auto-generated if omitted on write
        name:
          type: string
        sets:
          type: array
          items:
            $ref: '#/components/schemas/ExerciseSet'
        duration:
          type: integer
          description: Duration in minutes (optional, for cardio)
          nullable: true

    HealthLog:
      type: object
      properties:
        user_id:
          type: string
        log_date:
          type: string
          format: date
        exercises:
          type: array
          items:
            $ref: '#/components/schemas/Exercise'
        notes:
          type: string
        created_at:
          type: string
          format: date-time
        updated_at:
          type: string
          format: date-time

    HealthSummary:
      type: object
      description: Returned by list endpoint
      properties:
        user_id:
          type: string
        log_date:
          type: string
          format: date
        exercise_count:
          type: integer
        notes:
          type: string
        created_at:
          type: string
          format: date-time
        updated_at:
          type: string
          format: date-time

    HealthWrite:
      type: object
      properties:
        exercises:
          type: array
          items:
            $ref: '#/components/schemas/Exercise'
        notes:
          type: string

    # ── Nutrition ─────────────────────────────────────────────────────────────

    Meal:
      type: object
      properties:
        id:
          type: string
          format: uuid
          description: Auto-generated if omitted on write
        name:
          type: string
        calories:
          type: number
        protein:
          type: number
          description: Grams
        carbs:
          type: number
          description: Grams
        fat:
          type: number
          description: Grams

    NutritionLog:
      type: object
      properties:
        user_id:
          type: string
        log_date:
          type: string
          format: date
        meals:
          type: array
          items:
            $ref: '#/components/schemas/Meal'
        notes:
          type: string
        created_at:
          type: string
          format: date-time
        updated_at:
          type: string
          format: date-time

    NutritionSummary:
      type: object
      description: Returned by list endpoint
      properties:
        user_id:
          type: string
        log_date:
          type: string
          format: date
        meal_count:
          type: integer
        total_cal:
          type: number
          description: Sum of all meal calories
        notes:
          type: string
        created_at:
          type: string
          format: date-time
        updated_at:
          type: string
          format: date-time

    NutritionWrite:
      type: object
      properties:
        meals:
          type: array
          items:
            $ref: '#/components/schemas/Meal'
        notes:
          type: string

    # ── Settings ──────────────────────────────────────────────────────────────

    Settings:
      type: object
      properties:
        user_id:
          type: string
        dark_mode:
          type: boolean
          default: false
        ntfy_url:
          type: string
          description: ntfy endpoint for push notifications (e.g. https://ntfy.sh/my-topic)
          default: ""
        autosave_seconds:
          type: integer
          enum: [60, 120, 300]
          default: 300
        timezone:
          type: string
          description: IANA timezone string (e.g. America/New_York)
          default: ""

    SettingsWrite:
      type: object
      properties:
        dark_mode:
          type: boolean
        ntfy_url:
          type: string
        autosave_seconds:
          type: integer
          enum: [60, 120, 300]
        timezone:
          type: string

    # ── Home / Admin ──────────────────────────────────────────────────────────

    CostBreakdown:
      type: object
      properties:
        startDate:
          type: string
          format: date
        endDate:
          type: string
          format: date
        totalCost:
          type: number
          description: USD
        groupBy:
          type: object
          additionalProperties:
            type: number
          description: Cost per AWS service name in USD

    AdminStats:
      type: object
      properties:
        tables:
          type: object
          additionalProperties:
            type: object
            properties:
              itemCount:
                type: integer
              sizeBytes:
                type: integer
        s3:
          type: object
          additionalProperties:
            type: object
            properties:
              sizeBytes:
                type: integer
              objectCount:
                type: integer

# ── Tags (navigation grouping) ────────────────────────────────────────────────

tags:
  - name: Journal
    description: Daily journal entries
  - name: Goals
    description: Long-term goals
  - name: Tasks
    description: Tasks and folders
  - name: Notes
    description: Markdown notes, folders, images, and file attachments
  - name: Habits
    description: Daily habit tracking with streak calculation
  - name: Health
    description: Exercise logs
  - name: Nutrition
    description: Meal and macro logs
  - name: Settings
    description: User preferences and notification configuration
  - name: Home
    description: Dashboard data — AWS cost breakdown
  - name: Admin
    description: Admin-only statistics
  - name: Export
    description: Bulk data export

# ── Paths ─────────────────────────────────────────────────────────────────────

paths:

  # ── Journal ─────────────────────────────────────────────────────────────────

  /journal:
    get:
      tags: [Journal]
      summary: List journal entries
      description: Returns all entries newest-first. Pass `q` for full-text search on title, body, and tags. Summaries are returned (body truncated to 200 chars).
      parameters:
        - name: q
          in: query
          required: false
          schema:
            type: string
          description: Full-text search term
      responses:
        "200":
          description: Array of journal summaries
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/JournalSummary'

  /journal/{date}:
    parameters:
      - name: date
        in: path
        required: true
        schema:
          type: string
          format: date
        example: "2024-03-15"
    get:
      tags: [Journal]
      summary: Get entry by date
      responses:
        "200":
          description: Full journal entry
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/JournalEntry'
        "404":
          description: No entry for that date
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Error'
    put:
      tags: [Journal]
      summary: Create or update entry for a date
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/JournalWrite'
      responses:
        "200":
          description: Updated entry
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/JournalEntry'
        "201":
          description: Created entry
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/JournalEntry'
    delete:
      tags: [Journal]
      summary: Delete entry
      responses:
        "204":
          description: Deleted
        "404":
          description: Not found
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Error'

  # ── Goals ────────────────────────────────────────────────────────────────────

  /goals:
    get:
      tags: [Goals]
      summary: List all goals
      responses:
        "200":
          description: Array of goals
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/Goal'
    post:
      tags: [Goals]
      summary: Create a goal
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/GoalWrite'
      responses:
        "201":
          description: Created goal
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Goal'

  /goals/{id}:
    parameters:
      - name: id
        in: path
        required: true
        schema:
          type: string
          format: uuid
    get:
      tags: [Goals]
      summary: Get a goal
      responses:
        "200":
          description: Goal
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Goal'
        "404":
          description: Not found
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Error'
    put:
      tags: [Goals]
      summary: Update a goal
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/GoalWrite'
      responses:
        "200":
          description: Updated goal
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Goal'
    delete:
      tags: [Goals]
      summary: Delete a goal
      responses:
        "204":
          description: Deleted

  # ── Tasks ────────────────────────────────────────────────────────────────────

  /tasks:
    get:
      tags: [Tasks]
      summary: List all tasks
      responses:
        "200":
          description: Array of tasks
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/Task'
    post:
      tags: [Tasks]
      summary: Create a task
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/TaskWrite'
      responses:
        "201":
          description: Created task
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Task'

  /tasks/{id}:
    parameters:
      - name: id
        in: path
        required: true
        schema:
          type: string
          format: uuid
    get:
      tags: [Tasks]
      summary: Get a task
      responses:
        "200":
          description: Task
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Task'
        "404":
          description: Not found
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Error'
    put:
      tags: [Tasks]
      summary: Update a task
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/TaskWrite'
      responses:
        "200":
          description: Updated task
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Task'
    delete:
      tags: [Tasks]
      summary: Delete a task
      responses:
        "204":
          description: Deleted

  /tasks/folders:
    get:
      tags: [Tasks]
      summary: List all task folders
      responses:
        "200":
          description: Array of folders
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/TaskFolder'
    post:
      tags: [Tasks]
      summary: Create a task folder
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/TaskFolderWrite'
      responses:
        "201":
          description: Created folder
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/TaskFolder'

  /tasks/folders/{id}:
    parameters:
      - name: id
        in: path
        required: true
        schema:
          type: string
          format: uuid
    put:
      tags: [Tasks]
      summary: Update a task folder
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/TaskFolderWrite'
      responses:
        "200":
          description: Updated folder
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/TaskFolder'
    delete:
      tags: [Tasks]
      summary: Delete a task folder
      responses:
        "204":
          description: Deleted

  # ── Notes ────────────────────────────────────────────────────────────────────

  /notes:
    get:
      tags: [Notes]
      summary: List notes
      description: Returns all notes newest-first. Pass `q` for full-text search on title, body, and tags. Summaries are returned (body truncated to 200 chars).
      parameters:
        - name: q
          in: query
          required: false
          schema:
            type: string
      responses:
        "200":
          description: Array of note summaries
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/NoteSummary'
    post:
      tags: [Notes]
      summary: Create a note
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/NoteWrite'
      responses:
        "201":
          description: Created note
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Note'

  /notes/{id}:
    parameters:
      - name: id
        in: path
        required: true
        schema:
          type: string
          format: uuid
    get:
      tags: [Notes]
      summary: Get a note
      responses:
        "200":
          description: Note
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Note'
        "404":
          description: Not found
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Error'
    put:
      tags: [Notes]
      summary: Update a note
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/NoteWrite'
      responses:
        "200":
          description: Updated note
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Note'
    delete:
      tags: [Notes]
      summary: Delete a note
      responses:
        "204":
          description: Deleted

  /notes/folders:
    get:
      tags: [Notes]
      summary: List all note folders
      responses:
        "200":
          description: Array of folders
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/NoteFolder'
    post:
      tags: [Notes]
      summary: Create a note folder
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/NoteFolderWrite'
      responses:
        "201":
          description: Created folder
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/NoteFolder'

  /notes/folders/{id}:
    parameters:
      - name: id
        in: path
        required: true
        schema:
          type: string
          format: uuid
    put:
      tags: [Notes]
      summary: Update a note folder
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/NoteFolderWrite'
      responses:
        "200":
          description: Updated folder
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/NoteFolder'
    delete:
      tags: [Notes]
      summary: Delete a note folder
      responses:
        "204":
          description: Deleted

  /notes/images:
    post:
      tags: [Notes]
      summary: Request a presigned S3 URL to upload an inline image
      description: Returns a presigned PUT URL. Upload the image directly to S3 using that URL. Reference the returned `key` in your Markdown as the `?key=` query parameter on `GET /notes/images`.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [filename, content_type]
              properties:
                filename:
                  type: string
                content_type:
                  type: string
                  example: "image/png"
      responses:
        "200":
          description: Presigned upload URL and S3 key
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/PresignedUpload'
    get:
      tags: [Notes]
      summary: Retrieve an inline note image
      parameters:
        - name: key
          in: query
          required: true
          schema:
            type: string
          description: S3 object key returned by POST /notes/images
      responses:
        "302":
          description: Redirect to CloudFront image URL

  /notes/{id}/attachments:
    parameters:
      - name: id
        in: path
        required: true
        schema:
          type: string
          format: uuid
    post:
      tags: [Notes]
      summary: Upload a file attachment to a note
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [filename, content_type]
              properties:
                filename:
                  type: string
                content_type:
                  type: string
      responses:
        "201":
          description: Attachment record with presigned download URL
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/NoteAttachment'

  /notes/{id}/attachments/{att_id}:
    parameters:
      - name: id
        in: path
        required: true
        schema:
          type: string
          format: uuid
      - name: att_id
        in: path
        required: true
        schema:
          type: string
          format: uuid
    get:
      tags: [Notes]
      summary: Download a file attachment
      responses:
        "302":
          description: Redirect to presigned S3 download URL
    delete:
      tags: [Notes]
      summary: Delete a file attachment
      responses:
        "204":
          description: Deleted

  # ── Habits ───────────────────────────────────────────────────────────────────

  /habits:
    get:
      tags: [Habits]
      summary: List all habits
      description: Returns habits with computed 30-day history, current streak, best streak, and today's completion status.
      responses:
        "200":
          description: Array of habits
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/Habit'
    post:
      tags: [Habits]
      summary: Create a habit
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/HabitWrite'
      responses:
        "201":
          description: Created habit
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Habit'

  /habits/{id}:
    parameters:
      - name: id
        in: path
        required: true
        schema:
          type: string
          format: uuid
    put:
      tags: [Habits]
      summary: Update a habit (name and/or notify_time)
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/HabitWrite'
      responses:
        "200":
          description: Updated habit
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Habit'
    delete:
      tags: [Habits]
      summary: Delete a habit and all its logs
      responses:
        "204":
          description: Deleted

  /habits/{id}/toggle:
    parameters:
      - name: id
        in: path
        required: true
        schema:
          type: string
          format: uuid
    post:
      tags: [Habits]
      summary: Toggle completion for a date
      description: Toggles the habit's done state for today (UTC) or a specified past date. Idempotent — calling twice returns to the previous state.
      parameters:
        - name: date
          in: query
          required: false
          schema:
            type: string
            format: date
          description: Date to toggle (defaults to today UTC)
      responses:
        "200":
          description: Updated habit with new history
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Habit'

  # ── Health ───────────────────────────────────────────────────────────────────

  /health:
    get:
      tags: [Health]
      summary: List all exercise logs
      responses:
        "200":
          description: Array of health log summaries
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/HealthSummary'

  /health/{date}:
    parameters:
      - name: date
        in: path
        required: true
        schema:
          type: string
          format: date
        example: "2024-03-15"
    get:
      tags: [Health]
      summary: Get exercise log for a date
      responses:
        "200":
          description: Full exercise log
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/HealthLog'
        "404":
          description: No log for that date
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Error'
    put:
      tags: [Health]
      summary: Create or update exercise log for a date
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/HealthWrite'
      responses:
        "200":
          description: Updated log
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/HealthLog'
        "201":
          description: Created log
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/HealthLog'
    delete:
      tags: [Health]
      summary: Delete exercise log
      responses:
        "204":
          description: Deleted

  # ── Nutrition ────────────────────────────────────────────────────────────────

  /nutrition:
    get:
      tags: [Nutrition]
      summary: List all nutrition logs
      responses:
        "200":
          description: Array of nutrition summaries
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/NutritionSummary'

  /nutrition/{date}:
    parameters:
      - name: date
        in: path
        required: true
        schema:
          type: string
          format: date
        example: "2024-03-15"
    get:
      tags: [Nutrition]
      summary: Get nutrition log for a date
      responses:
        "200":
          description: Full nutrition log
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/NutritionLog'
        "404":
          description: No log for that date
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Error'
    put:
      tags: [Nutrition]
      summary: Create or update nutrition log for a date
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/NutritionWrite'
      responses:
        "200":
          description: Updated log
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/NutritionLog'
        "201":
          description: Created log
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/NutritionLog'
    delete:
      tags: [Nutrition]
      summary: Delete nutrition log
      responses:
        "204":
          description: Deleted

  # ── Settings ─────────────────────────────────────────────────────────────────

  /settings:
    get:
      tags: [Settings]
      summary: Get user settings
      responses:
        "200":
          description: Settings object (defaults applied for missing fields)
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Settings'
    put:
      tags: [Settings]
      summary: Update user settings
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/SettingsWrite'
      responses:
        "200":
          description: Updated settings
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Settings'

  /settings/test-notification:
    post:
      tags: [Settings]
      summary: Send a test ntfy notification
      description: Sends a sample push notification to the `ntfy_url` currently saved in the user's settings. Returns an error if `ntfy_url` is not configured.
      responses:
        "200":
          description: Notification sent
          content:
            application/json:
              schema:
                type: object
                properties:
                  message:
                    type: string
        "400":
          description: ntfy_url not configured
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Error'

  # ── Home ─────────────────────────────────────────────────────────────────────

  /home/costs:
    get:
      tags: [Home]
      summary: Get AWS cost breakdown for the current month
      description: Calls the AWS Cost Explorer API and returns costs grouped by service. Requires Cost Explorer enabled and the project tagged with a matching `Project` tag. Each call costs ~$0.01.
      responses:
        "200":
          description: Cost breakdown
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/CostBreakdown'

  # ── Admin ────────────────────────────────────────────────────────────────────

  /admin/stats:
    get:
      tags: [Admin]
      summary: Get admin statistics
      description: Returns DynamoDB table sizes and S3 bucket usage. Intended for admin users only.
      responses:
        "200":
          description: Admin statistics
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/AdminStats'

  # ── Export ───────────────────────────────────────────────────────────────────

  /export:
    get:
      tags: [Export]
      summary: Download all user data as a ZIP file
      description: |
        Exports all features (tasks, notes, journal, habits, health, nutrition, goals) as Markdown files.
        Notes preserve folder hierarchy. Journal entries include YAML frontmatter.
        File attachments are included. Returns a binary ZIP.
      responses:
        "200":
          description: ZIP archive of all user data
          content:
            application/zip:
              schema:
                type: string
                format: binary
