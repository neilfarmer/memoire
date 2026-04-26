openapi: 3.0.3
info:
  title: Memoire API
  description: |
    Personal productivity API for tasks, notes, habits, journal, health, nutrition, goals,
    bookmarks, favorites, feeds, finances, diagrams, and an AI assistant.

    Most endpoints require a valid JWT in the `Authorization: Bearer <token>` header
    (issued by Cognito) or a Personal Access Token with the `pat_` prefix.
    Auth endpoints (`/auth/*`) are public.
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
        progress:
          type: integer
          minimum: 0
          maximum: 100
          default: 0
          description: Completion percent (0-100)
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
        progress:
          type: integer
          minimum: 0
          maximum: 100

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

    RecurrenceRule:
      type: object
      description: Repeat template for recurring tasks. Children inherit the parent's local time-of-day.
      required: [freq]
      properties:
        freq:
          type: string
          enum: [daily, weekly, weekdays]
        interval:
          type: integer
          minimum: 1
          maximum: 365
          default: 1
        by_weekday:
          type: array
          items:
            type: integer
            minimum: 1
            maximum: 7
          description: ISO weekday numbers (1=Mon..7=Sun). Optional refinement for weekly freq.
        until:
          type: string
          format: date
          nullable: true

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
        tags:
          type: array
          items:
            type: string
        scheduled_start:
          type: string
          format: date-time
          nullable: true
          description: ISO 8601 UTC datetime aligned to a 30-minute slot.
        duration_minutes:
          type: integer
          nullable: true
          description: Estimated/scheduled block length in minutes. Multiple of 30, max 480.
        recurrence_rule:
          $ref: '#/components/schemas/RecurrenceRule'
        recurrence_parent_id:
          type: string
          format: uuid
          nullable: true
          description: Set on auto-materialised child instances of a recurring task.
        reschedule_count:
          type: integer
          description: Number of times the watcher has bumped this task after a missed slot.
        blocked_reason:
          type: string
          nullable: true
          description: Set to "max_reschedules" when the watcher gives up bumping the task.
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
        tags:
          type: array
          items:
            type: string
        scheduled_start:
          type: string
          format: date-time
          nullable: true
        duration_minutes:
          type: integer
          minimum: 5
          maximum: 480
          nullable: true
        recurrence_rule:
          $ref: '#/components/schemas/RecurrenceRule'
        notifications:
          $ref: '#/components/schemas/TaskNotifications'

    AutoScheduleRequest:
      type: object
      properties:
        task_ids:
          type: array
          items:
            type: string
            format: uuid
          description: Limit scheduling to these task ids. Default is all eligible (todo/in_progress, no schedule, no recurrence rule).
        horizon_days:
          type: integer
          minimum: 1
          maximum: 60
        respect_priority:
          type: boolean
          default: true

    AutoScheduleResponse:
      type: object
      properties:
        scheduled:
          type: array
          items:
            type: object
            properties:
              task_id:           { type: string, format: uuid }
              title:             { type: string }
              scheduled_start:   { type: string, format: date-time }
              duration_minutes:  { type: integer }
        skipped:
          type: array
          items:
            type: object
            properties:
              task_id: { type: string, format: uuid }
              reason:  { type: string, enum: [no free slot, past due date] }

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
        time_of_day:
          type: string
          enum: [morning, afternoon, evening, anytime]
          default: anytime
          description: When the habit is typically performed
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
        time_of_day:
          type: string
          enum: [morning, afternoon, evening, anytime]

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
          description: ntfy endpoint for push notifications (e.g. https://ntfy.sh/my-topic). HTTPS only; must not resolve to a private or reserved address.
          default: ""
        autosave_seconds:
          type: integer
          enum: [60, 120, 300]
          default: 300
        timezone:
          type: string
          description: IANA timezone string (e.g. America/New_York)
          default: ""
        display_name:
          type: string
          description: Name shown in UI greetings
          default: ""
        pal_name:
          type: string
          description: Custom name for the AI assistant (default "Pip")
          default: ""
        profile_inference_hours:
          type: integer
          description: Hours between watcher profile-inference runs
          default: 24
        home_finances_widget:
          type: boolean
          description: Show finances widget on the home dashboard
          default: false
        chat_retention_days:
          type: integer
          minimum: 0
          maximum: 3650
          default: 30
          description: How long AI Pal chat messages are kept before TTL deletion. 0 = keep forever.

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
        display_name:
          type: string
        pal_name:
          type: string
        profile_inference_hours:
          type: integer
        home_finances_widget:
          type: boolean
        chat_retention_days:
          type: integer
          minimum: 0
          maximum: 3650

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

    # ── Diagrams ──────────────────────────────────────────────────────────────

    Diagram:
      type: object
      properties:
        diagram_id:
          type: string
          format: uuid
        title:
          type: string
        elements:
          type: array
          description: Excalidraw elements array
          items:
            type: object
        app_state:
          type: object
          description: Excalidraw application state
        created_at:
          type: string
          format: date-time
        updated_at:
          type: string
          format: date-time

    DiagramSummary:
      type: object
      description: Returned by list endpoint (no elements or app_state)
      properties:
        diagram_id:
          type: string
          format: uuid
        title:
          type: string
        created_at:
          type: string
          format: date-time
        updated_at:
          type: string
          format: date-time

    DiagramWrite:
      type: object
      properties:
        title:
          type: string
          maxLength: 200
        elements:
          type: array
          items:
            type: object
        app_state:
          type: object

    # ── Bookmarks ────────────────────────────────────────────────────────────

    Bookmark:
      type: object
      properties:
        user_id:
          type: string
        bookmark_id:
          type: string
          format: uuid
        url:
          type: string
        title:
          type: string
        favicon_url:
          type: string
        thumbnail_url:
          type: string
        tags:
          type: array
          items:
            type: string
        note:
          type: string
        favourited:
          type: boolean
        created_at:
          type: string
          format: date-time
        updated_at:
          type: string
          format: date-time

    BookmarkCreate:
      type: object
      required: [url]
      properties:
        url:
          type: string
          maxLength: 2048
          description: HTTP or HTTPS URL
        title:
          type: string
          maxLength: 500
        note:
          type: string
          maxLength: 10000
        tags:
          type: array
          maxItems: 20
          items:
            type: string
            maxLength: 100

    BookmarkUpdate:
      type: object
      properties:
        url:
          type: string
          maxLength: 2048
        title:
          type: string
          maxLength: 500
        note:
          type: string
          maxLength: 10000
        tags:
          type: array
          maxItems: 20
          items:
            type: string
            maxLength: 100
        favourited:
          type: boolean

    # ── Favorites ────────────────────────────────────────────────────────────

    Favorite:
      type: object
      properties:
        user_id:
          type: string
        favorite_id:
          type: string
          format: uuid
        url:
          type: string
        title:
          type: string
        feed_title:
          type: string
        image:
          type: string
        description:
          type: string
        published:
          type: string
          format: date-time
        tags:
          type: array
          items:
            type: string
        created_at:
          type: string
          format: date-time

    FavoriteCreate:
      type: object
      required: [url]
      properties:
        url:
          type: string
        title:
          type: string
          maxLength: 500
        feed_title:
          type: string
          maxLength: 200
        image:
          type: string
          maxLength: 2000
        description:
          type: string
          maxLength: 500
        published:
          type: string
          format: date-time
        tags:
          type: array
          maxItems: 20
          items:
            type: string
            maxLength: 50

    FavoriteTagUpdate:
      type: object
      required: [tags]
      properties:
        tags:
          type: array
          maxItems: 20
          items:
            type: string
            maxLength: 50

    # ── Feeds ────────────────────────────────────────────────────────────────

    Feed:
      type: object
      properties:
        user_id:
          type: string
        feed_id:
          type: string
          format: uuid
        url:
          type: string
        created_at:
          type: string
          format: date-time

    FeedCreate:
      type: object
      required: [url]
      properties:
        url:
          type: string
          description: RSS/Atom feed URL or page URL with feed autodiscovery

    FeedArticle:
      type: object
      properties:
        feed_id:
          type: string
        feed_title:
          type: string
        title:
          type: string
        url:
          type: string
        description:
          type: string
          description: Max 300 chars, HTML stripped
        image:
          type: string
        published:
          type: string

    ArticleText:
      type: object
      properties:
        text:
          type: string
          description: Plain text, max 8000 chars
        url:
          type: string

    # ── Finances ─────────────────────────────────────────────────────────────

    Debt:
      type: object
      properties:
        user_id:
          type: string
        debt_id:
          type: string
          format: uuid
        name:
          type: string
        type:
          type: string
          enum: [auto_loan, mortgage, credit_card, student_loan, personal_loan, line_of_credit, other]
        balance:
          type: string
          description: Decimal string
        original_balance:
          type: string
        apr:
          type: string
        monthly_payment:
          type: string
        notes:
          type: string
        created_at:
          type: string
          format: date-time
        updated_at:
          type: string
          format: date-time
        annual_interest:
          type: string
          description: Computed, 2 decimal places
        payoff_months:
          type: integer
          nullable: true
          description: Months until paid off, null if never
        total_interest_remaining:
          type: string
          nullable: true
        total_months:
          type: integer
          nullable: true
          description: Months from original balance (for progress tracking)

    DebtWrite:
      type: object
      required: [name, type, balance, apr, monthly_payment]
      properties:
        name:
          type: string
          maxLength: 200
        type:
          type: string
          enum: [auto_loan, mortgage, credit_card, student_loan, personal_loan, line_of_credit, other]
        balance:
          type: number
          exclusiveMinimum: 0
        apr:
          type: number
          minimum: 0
        monthly_payment:
          type: number
          exclusiveMinimum: 0
        original_balance:
          type: number
          description: Defaults to balance if omitted
        notes:
          type: string
          maxLength: 1000

    Income:
      type: object
      properties:
        user_id:
          type: string
        income_id:
          type: string
          format: uuid
        name:
          type: string
        amount:
          type: string
          description: Decimal string
        frequency:
          type: string
          enum: [monthly, biweekly, weekly, annual]
        notes:
          type: string
        created_at:
          type: string
          format: date-time
        updated_at:
          type: string
          format: date-time
        monthly_amount:
          type: string
          description: Computed, normalized to monthly

    IncomeWrite:
      type: object
      required: [name, amount, frequency]
      properties:
        name:
          type: string
          maxLength: 200
        amount:
          type: number
          exclusiveMinimum: 0
        frequency:
          type: string
          enum: [monthly, biweekly, weekly, annual]
        notes:
          type: string
          maxLength: 1000

    FixedExpense:
      type: object
      properties:
        user_id:
          type: string
        expense_id:
          type: string
          format: uuid
        name:
          type: string
        amount:
          type: string
          description: Decimal string
        frequency:
          type: string
          enum: [monthly, biweekly, weekly, annual]
        category:
          type: string
          enum: [housing, utilities, subscriptions, insurance, food, transport, healthcare, other]
        due_day:
          type: integer
          minimum: 1
          maximum: 31
          nullable: true
        notes:
          type: string
        created_at:
          type: string
          format: date-time
        updated_at:
          type: string
          format: date-time
        monthly_amount:
          type: string
          description: Computed, normalized to monthly

    FixedExpenseWrite:
      type: object
      required: [name, amount, frequency, category]
      properties:
        name:
          type: string
          maxLength: 200
        amount:
          type: number
          exclusiveMinimum: 0
        frequency:
          type: string
          enum: [monthly, biweekly, weekly, annual]
        category:
          type: string
          enum: [housing, utilities, subscriptions, insurance, food, transport, healthcare, other]
        due_day:
          type: integer
          minimum: 1
          maximum: 31
          nullable: true
        notes:
          type: string
          maxLength: 1000

    FinancesSummary:
      type: object
      properties:
        total_monthly_income:
          type: string
        total_monthly_expenses:
          type: string
        total_monthly_debt_payments:
          type: string
        total_monthly_outflow:
          type: string
        net_monthly_cash_flow:
          type: string
        total_debt_balance:
          type: string
        total_annual_interest:
          type: string
        debts:
          type: array
          items:
            $ref: '#/components/schemas/Debt'
        income:
          type: array
          items:
            $ref: '#/components/schemas/Income'
        expenses:
          type: array
          items:
            $ref: '#/components/schemas/FixedExpense'

    # ── Tokens ───────────────────────────────────────────────────────────────

    Token:
      type: object
      properties:
        user_id:
          type: string
        token_id:
          type: string
          format: uuid
        name:
          type: string
        created_at:
          type: string
          format: date-time

    TokenCreate:
      type: object
      required: [name]
      properties:
        name:
          type: string
          maxLength: 100

    TokenCreated:
      type: object
      description: Returned once on creation; the plaintext token is never shown again
      properties:
        user_id:
          type: string
        token_id:
          type: string
          format: uuid
        name:
          type: string
        created_at:
          type: string
          format: date-time
        token:
          type: string
          description: "Plaintext PAT with `pat_` prefix (only returned at creation time)"

    # ── Auth ──────────────────────────────────────────────────────────────────

    AuthCallback:
      type: object
      required: [code, redirect_uri, code_verifier]
      properties:
        code:
          type: string
          description: Cognito authorization code
        redirect_uri:
          type: string
        code_verifier:
          type: string
          description: PKCE code verifier

    AuthUser:
      type: object
      properties:
        email:
          type: string
        sub:
          type: string
          description: Cognito user ID
        exp:
          type: integer
          description: JWT expiration (Unix timestamp)

    # ── Assistant ─────────────────────────────────────────────────────────────

    ChatRequest:
      type: object
      required: [message]
      properties:
        message:
          type: string
        model:
          type: string
          enum: ["us.amazon.nova-lite-v1:0", "us.amazon.nova-pro-v1:0"]
          default: "us.amazon.nova-lite-v1:0"
        local_date:
          type: string
          format: date
          description: Current date for context
        no_history:
          type: boolean
          description: Skip saving to conversation history (one-shot mode; does not auto-create a thread)
        conversation_id:
          type: string
          format: uuid
          description: Thread to continue. Omit to auto-create a new thread titled from the first message.

    ChatResponse:
      type: object
      properties:
        reply:
          type: string
        tools_used:
          type: array
          items:
            type: string
        conversation_id:
          type: string
          format: uuid
          description: Thread the message was saved under (null when `no_history` was true).
          nullable: true

    ConversationMessage:
      type: object
      properties:
        role:
          type: string
          enum: [user, assistant]
        content:
          type: string
        msg_id:
          type: string
          description: Stable message identifier within the thread

    ConversationMeta:
      type: object
      properties:
        conversation_id:
          type: string
          format: uuid
        title:
          type: string
        created_at:
          type: string
          format: date-time
        updated_at:
          type: string
          format: date-time
        message_count:
          type: integer

    ConversationDetail:
      allOf:
        - $ref: '#/components/schemas/ConversationMeta'
        - type: object
          properties:
            messages:
              type: array
              items:
                $ref: '#/components/schemas/ConversationMessage'

    ConversationCreate:
      type: object
      properties:
        title:
          type: string
          maxLength: 200

    ConversationRename:
      type: object
      required: [title]
      properties:
        title:
          type: string
          maxLength: 200

    AssistantUsage:
      type: object
      properties:
        model_id:
          type: string
        invocations:
          type: integer
        input_tokens:
          type: integer
        output_tokens:
          type: integer

    AssistantMemory:
      type: object
      properties:
        master_context:
          type: string
        facts:
          type: object
          additionalProperties:
            type: string
        profile:
          type: object
          properties:
            name:
              type: string
            occupation:
              type: string
            summary:
              type: string
        ai_analysis:
          type: object
          properties:
            analysis:
              type: string
            generated_at:
              type: string
              format: date-time

    AssistantProfile:
      type: object
      properties:
        name:
          type: string
        occupation:
          type: string
        summary:
          type: string

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
  - name: Diagrams
    description: Excalidraw diagrams
  - name: Bookmarks
    description: Web bookmarks with metadata scraping
  - name: Favorites
    description: Saved feed articles
  - name: Feeds
    description: RSS/Atom feed subscriptions and articles
  - name: Finances
    description: Debts, income, and fixed expenses
  - name: Tokens
    description: Personal Access Token management (JWT-only)
  - name: Auth
    description: Authentication (public, no token required)
  - name: Assistant
    description: AI assistant (Pip) powered by Amazon Bedrock
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

  /tasks/calendar:
    get:
      tags: [Tasks]
      summary: List scheduled tasks within a date range
      description: Returns tasks whose `scheduled_start` falls in `[from, to]`. Used to keep week-view payloads small.
      parameters:
        - name: from
          in: query
          required: true
          schema: { type: string, format: date }
        - name: to
          in: query
          required: true
          schema: { type: string, format: date }
      responses:
        "200":
          description: Scheduled tasks in range
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/Task'
        "400":
          description: Missing or malformed range
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Error'

  /tasks/auto-schedule:
    post:
      tags: [Tasks]
      summary: Greedily fit unscheduled tasks into free working-hour slots
      description: |
        Sorts targets by (priority desc, due date asc, created_at asc) and walks
        the user's working-hour slots until each fits. Skips tasks that already
        have a `scheduled_start` unless requested explicitly via `task_ids`.
      requestBody:
        required: false
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/AutoScheduleRequest'
      responses:
        "200":
          description: Scheduling result
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/AutoScheduleResponse'

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
                size:
                  type: integer
                  description: File size in bytes (recommended so the server can enforce quota)
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
      description: Sends a sample push notification. Uses the optional `ntfy_url` from the request body if provided, otherwise falls back to the saved setting. Returns an error if neither is configured.
      requestBody:
        required: false
        content:
          application/json:
            schema:
              type: object
              properties:
                ntfy_url:
                  type: string
                  description: Optional URL to test; overrides the saved setting.
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

  # ── Diagrams ──────────────────────────────────────────────────────────────────

  /diagrams:
    get:
      tags: [Diagrams]
      summary: List all diagrams
      description: Returns diagram summaries (no elements or app_state).
      responses:
        "200":
          description: Array of diagram summaries
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/DiagramSummary'
    post:
      tags: [Diagrams]
      summary: Create a diagram
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/DiagramWrite'
      responses:
        "201":
          description: Created diagram
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Diagram'

  /diagrams/{id}:
    parameters:
      - name: id
        in: path
        required: true
        schema:
          type: string
          format: uuid
    get:
      tags: [Diagrams]
      summary: Get a diagram
      description: Returns full diagram including elements and app_state.
      responses:
        "200":
          description: Diagram with elements
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Diagram'
        "404":
          description: Not found
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Error'
    put:
      tags: [Diagrams]
      summary: Update a diagram
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/DiagramWrite'
      responses:
        "200":
          description: Updated diagram
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Diagram'
    delete:
      tags: [Diagrams]
      summary: Delete a diagram
      responses:
        "204":
          description: Deleted

  # ── Bookmarks ─────────────────────────────────────────────────────────────────

  /bookmarks:
    get:
      tags: [Bookmarks]
      summary: List all bookmarks
      description: Returns bookmarks sorted alphabetically by title. Supports filtering by tag and full-text search.
      parameters:
        - name: tag
          in: query
          required: false
          schema:
            type: string
          description: Filter by tag (case-insensitive)
        - name: q
          in: query
          required: false
          schema:
            type: string
          description: Search across title, url, description, and note
      responses:
        "200":
          description: Array of bookmarks
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/Bookmark'
    post:
      tags: [Bookmarks]
      summary: Create a bookmark
      description: Scrapes the URL for title, favicon, and thumbnail metadata.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/BookmarkCreate'
      responses:
        "201":
          description: Created bookmark
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Bookmark'

  /bookmarks/{id}:
    parameters:
      - name: id
        in: path
        required: true
        schema:
          type: string
          format: uuid
    get:
      tags: [Bookmarks]
      summary: Get a bookmark
      responses:
        "200":
          description: Bookmark
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Bookmark'
        "404":
          description: Not found
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Error'
    put:
      tags: [Bookmarks]
      summary: Update a bookmark
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/BookmarkUpdate'
      responses:
        "200":
          description: Updated bookmark
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Bookmark'
    delete:
      tags: [Bookmarks]
      summary: Delete a bookmark
      responses:
        "204":
          description: Deleted

  # ── Favorites ─────────────────────────────────────────────────────────────────

  /favorites:
    get:
      tags: [Favorites]
      summary: List all favorites
      responses:
        "200":
          description: Array of favorites
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/Favorite'
    post:
      tags: [Favorites]
      summary: Save an article as a favorite
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/FavoriteCreate'
      responses:
        "201":
          description: Created favorite
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Favorite'

  /favorites/{id}:
    parameters:
      - name: id
        in: path
        required: true
        schema:
          type: string
          format: uuid
    patch:
      tags: [Favorites]
      summary: Update favorite tags
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/FavoriteTagUpdate'
      responses:
        "200":
          description: Updated favorite
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Favorite'
    delete:
      tags: [Favorites]
      summary: Remove a favorite
      responses:
        "204":
          description: Deleted

  # ── Feeds ─────────────────────────────────────────────────────────────────────

  /feeds:
    get:
      tags: [Feeds]
      summary: List subscribed feeds
      responses:
        "200":
          description: Array of feeds
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/Feed'
    post:
      tags: [Feeds]
      summary: Subscribe to a feed
      description: Accepts an RSS/Atom URL or a page URL with feed autodiscovery. Max 20 feeds per user.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/FeedCreate'
      responses:
        "201":
          description: Created feed subscription
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Feed'

  /feeds/{id}:
    parameters:
      - name: id
        in: path
        required: true
        schema:
          type: string
          format: uuid
    delete:
      tags: [Feeds]
      summary: Unsubscribe from a feed
      responses:
        "204":
          description: Deleted

  /feeds/articles:
    get:
      tags: [Feeds]
      summary: Fetch articles from all subscribed feeds
      description: Articles are cached for 30 minutes. Pass `force=true` to refresh.
      parameters:
        - name: force
          in: query
          required: false
          schema:
            type: string
            enum: ["true", "1"]
          description: Force cache refresh
      responses:
        "200":
          description: Array of articles from all feeds
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/FeedArticle'

  /feeds/article-text:
    get:
      tags: [Feeds]
      summary: Get article plain text
      description: Fetches and extracts plain text from an article URL. Max 8000 chars.
      parameters:
        - name: url
          in: query
          required: true
          schema:
            type: string
      responses:
        "200":
          description: Article text
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ArticleText'

  /feeds/read:
    get:
      tags: [Feeds]
      summary: Get read article URLs
      responses:
        "200":
          description: Array of read article URLs
          content:
            application/json:
              schema:
                type: array
                items:
                  type: object
                  properties:
                    url:
                      type: string
    post:
      tags: [Feeds]
      summary: Mark an article as read
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [url]
              properties:
                url:
                  type: string
      responses:
        "200":
          description: Marked as read
          content:
            application/json:
              schema:
                type: object
                properties:
                  url:
                    type: string

  # ── Finances: Debts ───────────────────────────────────────────────────────────

  /debts:
    get:
      tags: [Finances]
      summary: List all debts
      responses:
        "200":
          description: Array of debts with computed fields
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/Debt'
    post:
      tags: [Finances]
      summary: Create a debt
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/DebtWrite'
      responses:
        "201":
          description: Created debt
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Debt'

  /debts/{id}:
    parameters:
      - name: id
        in: path
        required: true
        schema:
          type: string
          format: uuid
    put:
      tags: [Finances]
      summary: Update a debt
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/DebtWrite'
      responses:
        "200":
          description: Updated debt
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Debt'
    delete:
      tags: [Finances]
      summary: Delete a debt
      responses:
        "204":
          description: Deleted

  # ── Finances: Income ──────────────────────────────────────────────────────────

  /income:
    get:
      tags: [Finances]
      summary: List all income sources
      responses:
        "200":
          description: Array of income sources with computed monthly_amount
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/Income'
    post:
      tags: [Finances]
      summary: Create an income source
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/IncomeWrite'
      responses:
        "201":
          description: Created income
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Income'

  /income/{id}:
    parameters:
      - name: id
        in: path
        required: true
        schema:
          type: string
          format: uuid
    put:
      tags: [Finances]
      summary: Update an income source
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/IncomeWrite'
      responses:
        "200":
          description: Updated income
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Income'
    delete:
      tags: [Finances]
      summary: Delete an income source
      responses:
        "204":
          description: Deleted

  # ── Finances: Fixed Expenses ──────────────────────────────────────────────────

  /fixed-expenses:
    get:
      tags: [Finances]
      summary: List all fixed expenses
      responses:
        "200":
          description: Array of expenses with computed monthly_amount
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/FixedExpense'
    post:
      tags: [Finances]
      summary: Create a fixed expense
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/FixedExpenseWrite'
      responses:
        "201":
          description: Created expense
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/FixedExpense'

  /fixed-expenses/{id}:
    parameters:
      - name: id
        in: path
        required: true
        schema:
          type: string
          format: uuid
    put:
      tags: [Finances]
      summary: Update a fixed expense
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/FixedExpenseWrite'
      responses:
        "200":
          description: Updated expense
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/FixedExpense'
    delete:
      tags: [Finances]
      summary: Delete a fixed expense
      responses:
        "204":
          description: Deleted

  # ── Finances: Summary ─────────────────────────────────────────────────────────

  /finances/summary:
    get:
      tags: [Finances]
      summary: Get financial summary
      description: Returns all debts, income, and expenses with computed monthly totals and net cash flow.
      responses:
        "200":
          description: Financial summary
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/FinancesSummary'

  # ── Tokens ────────────────────────────────────────────────────────────────────

  /tokens:
    get:
      tags: [Tokens]
      summary: List personal access tokens
      description: Returns token metadata only (never exposes the token hash). Requires JWT authentication; PAT-authenticated requests are rejected with 403.
      responses:
        "200":
          description: Array of tokens
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/Token'
    post:
      tags: [Tokens]
      summary: Create a personal access token
      description: The plaintext token (prefixed with `pat_`) is returned once in the response and never stored or shown again.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/TokenCreate'
      responses:
        "201":
          description: Created token (includes plaintext PAT)
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/TokenCreated'

  /tokens/{id}:
    parameters:
      - name: id
        in: path
        required: true
        schema:
          type: string
          format: uuid
    delete:
      tags: [Tokens]
      summary: Revoke a personal access token
      responses:
        "204":
          description: Revoked

  # ── Auth ──────────────────────────────────────────────────────────────────────

  /auth/callback:
    post:
      tags: [Auth]
      summary: Exchange authorization code for tokens
      description: Completes the Cognito PKCE OAuth flow. Sets HttpOnly cookies for the JWT and refresh token.
      security: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/AuthCallback'
      responses:
        "200":
          description: Authenticated user info (tokens set as HttpOnly cookies)
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/AuthUser'

  /auth/refresh:
    post:
      tags: [Auth]
      summary: Refresh the JWT using the refresh token cookie
      security: []
      responses:
        "200":
          description: Refreshed user info (new JWT cookie set)
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/AuthUser'
        "401":
          description: No refresh token cookie or token expired
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Error'

  /auth/logout:
    post:
      tags: [Auth]
      summary: Clear authentication cookies
      security: []
      responses:
        "200":
          description: Logged out
          content:
            application/json:
              schema:
                type: object
                properties:
                  ok:
                    type: boolean

  # ── Assistant ─────────────────────────────────────────────────────────────────

  /assistant/chat:
    post:
      tags: [Assistant]
      summary: Send a message to the AI assistant
      description: Sends a message to the Bedrock-powered assistant. The assistant can call tools to read and modify tasks, notes, habits, goals, journal, nutrition, and exercise data.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ChatRequest'
      responses:
        "200":
          description: Assistant reply
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ChatResponse'

  /assistant/conversations:
    get:
      tags: [Assistant]
      summary: List saved chat threads
      description: Returns thread metadata (id, title, timestamps, message count) ordered by most-recent update. Messages themselves are fetched via `GET /assistant/conversations/{id}`.
      responses:
        "200":
          description: Array of thread metadata
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/ConversationMeta'
    post:
      tags: [Assistant]
      summary: Create an empty chat thread
      description: Explicit thread creation. Normally a thread is auto-created by `POST /assistant/chat` when no `conversation_id` is supplied.
      requestBody:
        required: false
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ConversationCreate'
      responses:
        "200":
          description: New thread metadata
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ConversationMeta'

  /assistant/conversations/{id}:
    parameters:
      - name: id
        in: path
        required: true
        schema:
          type: string
          format: uuid
    get:
      tags: [Assistant]
      summary: Get a chat thread with all messages
      responses:
        "200":
          description: Thread metadata plus ordered message list
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ConversationDetail'
        "404":
          description: Thread not found
    patch:
      tags: [Assistant]
      summary: Rename a chat thread
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ConversationRename'
      responses:
        "200":
          description: Updated
        "404":
          description: Thread not found
    delete:
      tags: [Assistant]
      summary: Delete a chat thread and all of its messages
      responses:
        "200":
          description: Deleted
        "404":
          description: Thread not found

  /assistant/history:
    get:
      tags: [Assistant]
      summary: Get conversation history (latest thread)
      description: Returns the ordered messages of the most-recent thread. Prefer `GET /assistant/conversations/{id}` when targeting a specific thread.
      responses:
        "200":
          description: Array of messages
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/ConversationMessage'
    delete:
      tags: [Assistant]
      summary: Clear conversation history
      responses:
        "204":
          description: History cleared

  /assistant/usage:
    get:
      tags: [Assistant]
      summary: Get Bedrock token usage
      responses:
        "200":
          description: Per-model usage statistics
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/AssistantUsage'

  /assistant/memory:
    get:
      tags: [Assistant]
      summary: Get assistant memory
      description: Returns master context, facts, profile, and AI analysis.
      responses:
        "200":
          description: Memory object
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/AssistantMemory'
    put:
      tags: [Assistant]
      summary: Update master context
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [master_context]
              properties:
                master_context:
                  type: string
      responses:
        "200":
          description: Updated memory
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/AssistantMemory'

  /assistant/memory/facts/{key}:
    parameters:
      - name: key
        in: path
        required: true
        schema:
          type: string
        description: Snake_case fact key (cannot start with __)
    put:
      tags: [Assistant]
      summary: Upsert a memory fact
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [value]
              properties:
                value:
                  type: string
      responses:
        "200":
          description: Updated memory
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/AssistantMemory'

  /assistant/memory/{key}:
    parameters:
      - name: key
        in: path
        required: true
        schema:
          type: string
    delete:
      tags: [Assistant]
      summary: Delete a memory fact
      responses:
        "204":
          description: Deleted

  /assistant/profile:
    get:
      tags: [Assistant]
      summary: Get user profile
      responses:
        "200":
          description: Profile
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/AssistantProfile'
    put:
      tags: [Assistant]
      summary: Update profile fields
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/AssistantProfile'
      responses:
        "200":
          description: Updated profile
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/AssistantProfile'

  /assistant/profile/analyze:
    post:
      tags: [Assistant]
      summary: Generate AI analysis of user profile
      description: Uses Bedrock to analyze the user's profile and stored facts.
      responses:
        "200":
          description: Analysis result
          content:
            application/json:
              schema:
                type: object
                properties:
                  analysis:
                    type: string
                  generated_at:
                    type: string
                    format: date-time
