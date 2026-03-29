"""
Backend Skill: NestJS patterns for enterprise Node.js applications.
Mirrors skills/backend/api_patterns.py structure — patterns, templates, checklists.
"""

# ─────────────────────────────────────────────────────────────────────────────
# NestJS Controller Pattern
# ─────────────────────────────────────────────────────────────────────────────

NEST_CONTROLLER_TEMPLATE = '''
import {
  Controller,
  Get,
  Post,
  Put,
  Patch,
  Delete,
  Param,
  Body,
  Query,
  HttpCode,
  HttpStatus,
  UseGuards,
  UseInterceptors,
} from '@nestjs/common'
import { UsersService } from './users.service'
import { CreateUserDto } from './dto/create-user.dto'
import { UpdateUserDto } from './dto/update-user.dto'
import { JwtAuthGuard } from '../auth/jwt-auth.guard'
import { RolesGuard } from '../auth/roles.guard'
import { Roles } from '../auth/roles.decorator'
import { LoggingInterceptor } from '../logging/logging.interceptor'

@Controller('users')
@UseInterceptors(LoggingInterceptor)  // Log all requests in this controller
export class UsersController {
  constructor(private readonly usersService: UsersService) {}

  @Get()
  @HttpCode(HttpStatus.OK)
  async findAll(
    @Query('skip') skip?: number,
    @Query('limit') limit?: number,
  ): Promise<{ data: UserResponse[]; total: number }> {
    return this.usersService.findAll(skip, limit)
  }

  @Get(':id')
  @HttpCode(HttpStatus.OK)
  async findOne(@Param('id', ParseUUIDPipe) id: string): Promise<UserResponse> {
    return this.usersService.findOne(id)
  }

  @Post()
  @HttpCode(HttpStatus.CREATED)
  async create(@Body() createUserDto: CreateUserDto): Promise<UserResponse> {
    return this.usersService.create(createUserDto)
  }

  @Patch(':id')
  @HttpCode(HttpStatus.OK)
  @UseGuards(JwtAuthGuard)  // Require authentication
  @Roles('admin', 'user')   // RBAC: only admin or owner
  async update(
    @Param('id', ParseUUIDPipe) id: string,
    @Body() updateUserDto: UpdateUserDto,
  ): Promise<UserResponse> {
    return this.usersService.update(id, updateUserDto)
  }

  @Delete(':id')
  @HttpCode(HttpStatus.NO_CONTENT)
  @UseGuards(JwtAuthGuard, RolesGuard)
  @Roles('admin')
  async remove(@Param('id', ParseUUIDPipe) id: string): Promise<void> {
    await this.usersService.remove(id)
  }
}
'''

# ─────────────────────────────────────────────────────────────────────────────
# NestJS Service Pattern (with caching)
# ─────────────────────────────────────────────────────────────────────────────

NEST_SERVICE_TEMPLATE = '''
import { Injectable, Logger, NotFoundException, BadRequestException } from '@nestjs/common'
import { InjectRepository } from '@nestjs/typeorm'
import { Repository } from 'typeorm'
import { Redis } from 'ioredis'
import { ConfigService } from '@nestjs/config'
import { User } from './user.entity'
import { CreateUserDto } from './dto/create-user.dto'
import { UpdateUserDto } from './dto/update-user.dto'
import { UserResponse } from './dto/user-response.dto'

@Injectable()
export class UsersService {
  private readonly logger = new Logger(UsersService.name)
  private readonly CACHE_TTL = 3600  // 1 hour
  private readonly CACHE_PREFIX = 'user:'

  constructor(
    @InjectRepository(User)
    private readonly userRepository: Repository<User>,
    @Inject('REDIS') private readonly redis: Redis,
    private readonly configService: ConfigService,
  ) {}

  async findAll(skip = 0, limit = 50): Promise<{ data: UserResponse[]; total: number }> {
    // Try cache first for small datasets
    const cacheKey = `users:list:${skip}:${limit}`
    const cached = await this.redis.get(cacheKey)
    if (cached) {
      this.logger.debug(`Cache hit for ${cacheKey}`)
      return JSON.parse(cached)
    }

    // DB query with pagination
    const [data, total] = await this.userRepository.findAndCount({
      skip,
      take: limit,
      order: { createdAt: 'DESC' },
    })

    const result = {
      data: data.map(user => this.toResponse(user)),
      total,
    }

    // Cache only if result set is small (< 1000 items)
    if (total < 1000) {
      await this.redis.setex(cacheKey, this.CACHE_TTL, JSON.stringify(result))
    }

    return result
  }

  async findOne(id: string): Promise<UserResponse> {
    // Check cache first (cache-aside pattern)
    const cacheKey = `${this.CACHE_PREFIX}${id}`
    const cached = await this.redis.get(cacheKey)
    if (cached) {
      this.logger.debug(`Cache hit for ${cacheKey}`)
      return JSON.parse(cached)
    }

    // DB hit
    const user = await this.userRepository.findOneBy({ id })
    if (!user) {
      throw new NotFoundException(`User ${id} not found`)
    }

    const response = this.toResponse(user)
    await this.redis.setex(cacheKey, this.CACHE_TTL, JSON.stringify(response))
    return response
  }

  async create(createUserDto: CreateUserDto): Promise<UserResponse> {
    // Check for existing email
    const existing = await this.userRepository.findOneBy({ email: createUserDto.email })
    if (existing) {
      throw new BadRequestException('User with this email already exists')
    }

    const user = this.userRepository.create(createUserDto)
    const saved = await this.userRepository.save(user)

    // Invalidate list cache
    await this.redis.del('users:list:*')

    return this.toResponse(saved)
  }

  async update(id: string, updateUserDto: UpdateUserDto): Promise<UserResponse> {
    const user = await this.userRepository.findOneBy({ id })
    if (!user) {
      throw new NotFoundException(`User ${id} not found`)
    }

    // Prevent email duplication if email is being updated
    if (updateUserDto.email && updateUserDto.email !== user.email) {
      const existing = await this.userRepository.findOneBy({ email: updateUserDto.email })
      if (existing && existing.id !== id) {
        throw new BadRequestException('User with this email already exists')
      }
    }

    Object.assign(user, updateUserDto, { updatedAt: new Date() })
    const saved = await this.userRepository.save(user)

    // Invalidate cache
    await this.redis.del(`${this.CACHE_PREFIX}${id}`)
    await this.redis.del('users:list:*')

    return this.toResponse(saved)
  }

  async remove(id: string): Promise<void> {
    const user = await this.userRepository.findOneBy({ id })
    if (!user) {
      throw new NotFoundException(`User ${id} not found`)
    }

    // Soft delete pattern (if using isDeleted flag)
    user.isDeleted = true
    user.deletedAt = new Date()
    await this.userRepository.save(user)

    // Invalidate cache
    await this.redis.del(`${this.CACHE_PREFIX}${id}`)
    await this.redis.del('users:list:*')
  }

  private toResponse(user: User): UserResponse {
    return {
      id: user.id,
      email: user.email,
      name: user.name,
      createdAt: user.createdAt.toISOString(),
      updatedAt: user.updatedAt?.toISOString(),
    }
  }
}
'''

# ─────────────────────────────────────────────────────────────────────────────
# DTO Validation Patterns (class-validator + class-transformer)
# ─────────────────────────────────────────────────────────────────────────────

NEST_DTO_VALIDATION = '''
import { IsEmail, IsString, MinLength, IsOptional, IsEnum, IsUUID, IsNumberString } from 'class-validator'
import { Type } from 'class-transformer'
import { IsDate } from 'class-validator'

// Create DTO — all required fields
export class CreateUserDto {
  @IsEmail({}, { message: 'Email must be valid' })
  @IsString()
  email: string

  @IsString()
  @MinLength(8, { message: 'Password must be at least 8 characters' })
  password: string

  @IsString()
  @IsOptional()
  name?: string

  @IsEnum(['free', 'pro', 'enterprise'])
  @IsOptional()
  plan?: 'free' | 'pro' | 'enterprise'
}

// Update DTO — all optional (partial update)
export class UpdateUserDto {
  @IsString()
  @IsOptional()
  name?: string

  @IsEmail({}, { message: 'Email must be valid' })
  @IsOptional()
  email?: string

  @IsNumberString({}, { message: 'Must be a positive integer' })
  @IsOptional()
  age?: number
}

// Query DTO for filtering
export class UsersQueryDto {
  @IsOptional()
  @IsString()
  search?: string

  @IsOptional()
  @Type(() => Number)
  @IsNumberString(undefined, { message: 'Must be an integer' })
  skip?: number

  @IsOptional()
  @Type(() => Number)
  @IsNumberString(undefined, { message: 'Must be an integer' })
  limit?: number

  @IsOptional()
  @IsEnum(['asc', 'desc'])
  sortBy?: 'asc' | 'desc'
}

// In main.ts, enable global validation pipe:
// app.useGlobalPipes(
//   new ValidationPipe({
//     transform: true,  // Auto-transform payloads to DTO instances
//     whitelist: true, // Strip unknown properties
//     forbidNonWhitelisted: true,  // Throw on unknown properties
//   })
// )
'''

# ─────────────────────────────────────────────────────────────────────────────
# Entity/Model Patterns (TypeORM)
# ─────────────────────────────────────────────────────────────────────────────

NEST_ENTITY_PATTERN = '''
import {
  Entity,
  PrimaryGeneratedColumn,
  Column,
  CreateDateColumn,
  UpdateDateColumn,
  DeleteDateColumn,
  Index,
  Unique,
} from 'typeorm'

@Entity('users')
@Unique(['email'])
export class User {
  @PrimaryGeneratedColumn('uuid')
  id: string

  @Column({ type: 'varchar', length: 255, unique: true })
  @Index()
  email: string

  @Column({ type: 'varchar', length: 255, select: false })  // Never select by default
  passwordHash: string

  @Column({ type: 'varchar', length: 100, nullable: true })
  name: string

  @Column({
    type: 'enum',
    enum: ['free', 'pro', 'enterprise'],
    default: 'free',
  })
  plan: 'free' | 'pro' | 'enterprise'

  @Column({ type: 'boolean', default: false })
  isDeleted: boolean

  @CreateDateColumn({ type: 'timestamp with time zone' })
  createdAt: Date

  @UpdateDateColumn({ type: 'timestamp with time zone' })
  updatedAt: Date

  @DeleteDateColumn({ type: 'timestamp with time zone' })
  deletedAt: Date

  // Relations (example: user has many sessions)
  // @OneToMany(() => Session, session => session.user)
  // sessions: Session[]
}

// Soft delete filter: automatically filter out deleted entities
// In UserModule providers:
// {
//   provide: 'USER_REPOSITORY',
//   useFactory: (connection: Connection) =>
//     connection.getRepository(User).createQueryBuilder('user')
//       .where('user.isDeleted = :isDeleted', { isDeleted: false }),
// }
'''

# ─────────────────────────────────────────────────────────────────────────────
# Authentication Patterns (JWT + Passport)
# ─────────────────────────────────────────────────────────────────────────────

NEST_JWT_AUTH = '''
// auth/jwt.strategy.ts
import { ExtractJwt, Strategy } from 'passport-jwt'
import { PassportStrategy } from '@nestjs/passport'
import { Injectable, UnauthorizedException } from '@nestjs/common'
import { ConfigService } from '@nestjs/config'
import { UsersService } from '../users/users.service'

@Injectable()
export class JwtStrategy extends PassportStrategy(Strategy, 'jwt') {
  constructor(
    private configService: ConfigService,
    private usersService: UsersService,
  ) {
    super({
      jwtFromRequest: ExtractJwt.fromAuthHeaderAsBearerToken(),
      ignoreExpiration: false,
      secretOrKey: configService.get<string>('JWT_SECRET'),
    })
  }

  async validate(payload: JwtPayload) {
    // payload contains sub, email, iat, exp
    const user = await this.usersService.findOne(payload.sub)
    if (!user || user.isDeleted) {
      throw new UnauthorizedException()
    }
    return { userId: user.id, email: user.email, roles: user.roles }
  }
}

// auth/jwt-auth.guard.ts
import { Injectable } from '@nestjs/common'
import { AuthGuard } from '@nestjs/passport'

@Injectable()
export class JwtAuthGuard extends AuthGuard('jwt') {}

// auth/roles.decorator.ts
import { SetMetadata } from '@nestjs/common'

export const ROLES_KEY = 'roles'
export const Roles = (...roles: string[]) => SetMetadata(ROLES_KEY, roles)

// auth/roles.guard.ts
import { Injectable, CanActivate, ExecutionContext } from '@nestjs/common'
import { Reflector } from '@nestjs/core'

@Injectable()
export class RolesGuard implements CanActivate {
  constructor(private reflector: Reflector) {}

  canActivate(context: ExecutionContext): boolean {
    const requiredRoles = this.reflector.get<string[]>(ROLES_KEY, context.getHandler())
    if (!requiredRoles) return true

    const { user } = context.switchToHttp().getRequest()
    return requiredRoles.some(role => user.roles?.includes(role))
  }
}

// Usage on controller method:
// @UseGuards(JwtAuthGuard, RolesGuard)
// @Roles('admin', 'owner')
'''

NEST_REFRESH_TOKENS = '''
// auth/refresh-token.entity.ts
@Entity('refresh_tokens')
export class RefreshToken {
  @PrimaryGeneratedColumn('uuid')
  id: string

  @Column({ name: 'user_id', type: 'uuid' })
  userId: string

  @Column({ type: 'varchar', length: 500, unique: true })
  token: string

  @Column({ type: 'timestamp with time zone' })
  expiresAt: Date

  @Column({ type: 'timestamp with time zone' })
  createdAt: Date

  @ManyToOne(() => User, { eager: true })
  @JoinColumn({ name: 'user_id' })
  user: User
}

// On login: create refresh token with 7-day expiry, store hashed in DB
// On refresh endpoint: verify token, issue new access + refresh, revoke old refresh
// On logout: delete refresh token from DB
'''

# ─────────────────────────────────────────────────────────────────────────────
# Configuration Management
# ─────────────────────────────────────────────────────────────────────────────

NEST_CONFIGURATION = '''
// Install: npm install @nestjs/config
// .env file at project root (never commit .env, use .env.example)

// config/configuration.ts
export default () => ({
  port: parseInt(process.env.PORT, 10) || 3000,
  database: {
    host: process.env.DB_HOST,
    port: parseInt(process.env.DB_PORT, 10) || 5432,
    name: process.env.DB_NAME,
    user: process.env.DB_USER,
    password: process.env.DB_PASSWORD,
  },
  redis: {
    host: process.env.REDIS_HOST,
    port: parseInt(process.env.REDIS_PORT, 10) || 6379,
  },
  jwt: {
    secret: process.env.JWT_SECRET,
    expiresIn: process.env.JWT_EXPIRES_IN || '15m',
    refreshExpiresIn: process.env.JWT_REFRESH_EXPIRES_IN || '7d',
  },
  cors: {
    origin: process.env.ALLOWED_ORIGINS?.split(',') || ['http://localhost:3000'],
    credentials: true,
  },
})

// app.module.ts
import { Module } from '@nestjs/common'
import { ConfigModule, ConfigService } from '@nestjs/config'
import configuration from './config/configuration'

@Module({
  imports: [
    ConfigModule.forRoot({
      load: [configuration],
      isGlobal: true,  // ConfigService injectable anywhere
    }),
  ],
})
export class AppModule {}
'''

# ─────────────────────────────────────────────────────────────────────────────
# Error Handling Patterns
# ─────────────────────────────────────────────────────────────────────────────

NEST_ERROR_HANDLING = '''
// exceptions/http-exception.filter.ts
import {
  ExceptionFilter,
  Catch,
  ArgumentsHost,
  HttpException,
  HttpStatus,
  Logger,
} from '@nestjs/common'
import { Request, Response } from 'express'

@Catch(HttpException)
export class HttpExceptionFilter implements ExceptionFilter {
  catch(exception: HttpException, host: ArgumentsHost) {
    const ctx = host.switchToHttp()
    const response = ctx.getResponse<Response>()
    const request = ctx.getRequest<Request>()

    const status = exception.getStatus()
    const message = exception.message instanceof Object
      ? exception.message
      : { message: exception.message }

    // Log error with context
    Logger.error(
      `${request.method} ${request.url}`,
      JSON.stringify({
        status,
        error: message,
        user: request.user?.userId,
        correlationId: request.headers['x-correlation-id'],
      }),
      'HttpExceptionFilter',
    )

    // Consistent error response format
    response.status(status).json({
      statusCode: status,
      timestamp: new Date().toISOString(),
      path: request.url,
      error: typeof message === 'string' ? message : message.message,
      details: message.details || null,
    })
  }
}

// Register globally in main.ts:
// app.useGlobalFilters(new HttpExceptionFilter())

// Custom business exceptions
export class BusinessException extends HttpException {
  constructor(message: string, public readonly code: string) {
    super({ message, code }, HttpStatus.BAD_REQUEST)
  }
}

// Usage: throw new BusinessException('Account locked', 'ACCOUNT_LOCKED')
'''

# ─────────────────────────────────────────────────────────────────────────────
# Repository Pattern (TypeORM)
# ─────────────────────────────────────────────────────────────────────────────

NEST_REPOSITORY_PATTERN = '''
// users/users.repository.ts
import { Injectable } from '@nestjs/common'
import { InjectRepository } from '@nestjs/typeorm'
import { Repository } from 'typeorm'
import { User } from './user.entity'
import { CreateUserDto } from './dto/create-user.dto'
import { UpdateUserDto } from './dto/update-user.dto'

@Injectable()
export class UsersRepository {
  constructor(
    @InjectRepository(User)
    private readonly userRepository: Repository<User>,
  ) {}

  async findById(id: string): Promise<User | null> {
    return this.userRepository.findOneBy({ id })
  }

  async findByEmail(email: string): Promise<User | null> {
    return this.userRepository.findOneBy({ email })
  }

  async create(createUserDto: CreateUserDto): Promise<User> {
    const user = this.userRepository.create(createUserDto)
    return this.userRepository.save(user)
  }

  async update(id: string, updateUserDto: UpdateUserDto): Promise<User> {
    const user = await this.userRepository.findOneBy({ id })
    if (!user) return null

    Object.assign(user, updateUserDto, { updatedAt: new Date() })
    return this.userRepository.save(user)
  }

  async delete(id: string): Promise<boolean> {
    const result = await this.userRepository.softDelete(id)
    return result.affected > 0
  }

  // Complex query with relations
  async findWithRoles(userId: string): Promise<UserWithRoles> {
    return this.userRepository
      .createQueryBuilder('user')
      .leftJoinAndSelect('user.roles', 'role')
      .where('user.id = :id', { id: userId })
      .andWhere('user.isDeleted', false)
      .getOne()
  }

  // Transaction example
  async createWithProfile(createUserDto: CreateUserDto, profileData: any): Promise<User> {
    return this.userRepository.manager.transaction(async (transactionalEntityManager) => {
      const user = transactionalEntityManager.create(createUserDto)
      await transactionalEntityManager.save(user)

      const profile = transactionalEntityManager.create({
        ...profileData,
        userId: user.id,
      })
      await transactionalEntityManager.save(profile)

      return user
    })
  }
}
'''

# ─────────────────────────────────────────────────────────────────────────────
# Testing Patterns (Jest)
# ─────────────────────────────────────────────────────────────────────────────

NEST_TESTING_PATTERNS = '''
import { Test, TestingModule } from '@nestjs/testing'
import { UsersService } from './users.service'
import { getRepositoryToken } from '@nestjs/typeorm'
import { Repository } from 'typeorm'
import { User } from './user.entity'
import { Redis } from 'ioredis'

describe('UsersService', () => {
  let service: UsersService
  let repository: Repository<User>
  let mockRedis: Redis

  const mockUser: User = {
    id: '123e4567-e89b-12d3-a456-426614174000',
    email: 'test@example.com',
    name: 'Test User',
    createdAt: new Date(),
    updatedAt: new Date(),
    isDeleted: false,
  }

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      providers: [
        UsersService,
        {
          provide: getRepositoryToken(User),
          useValue: {
            findOneBy: jest.fn(),
            save: jest.fn(),
            findAndCount: jest.fn(),
          },
        },
        {
          provide: 'REDIS',
          useValue: {
            get: jest.fn(),
            setex: jest.fn(),
            del: jest.fn(),
          },
        },
      ],
    }).compile()

    service = module.get<UsersService>(UsersService)
    repository = module.get<Repository<User>>(getRepositoryToken(User))
    mockRedis = module.get<Redis>('REDIS')
  })

  describe('findOne', () => {
    it('should return user when found', async () => {
      jest.spyOn(repository, 'findOneBy').mockResolvedValueOnce(mockUser)
      jest.spyOn(mockRedis, 'get').mockResolvedValueOnce(null)
      jest.spyOn(mockRedis, 'setex').mockResolvedValueOnce('OK')

      const result = await service.findOne(mockUser.id)
      expect(result).toEqual(expect.objectContaining({
        id: mockUser.id,
        email: mockUser.email,
      }))
    })

    it('should throw NotFoundException when user not found', async () => {
      jest.spyOn(repository, 'findOneBy').mockResolvedValueOnce(null)

      await expect(service.findOne('nonexistent')).rejects.toThrow(NotFoundException)
    })
  })

  describe('create', () => {
    const createDto = { email: 'new@example.com', password: 'pass123', name: 'New User' }

    it('should create user and invalidate cache', async () => {
      jest.spyOn(repository, 'create').mockReturnValue({ ...createDto, id: 'new-id' } as any)
      jest.spyOn(repository, 'save').mockResolvedValueOnce({ id: 'new-id', ...createDto })
      jest.spyOn(mockRedis, 'del').mockResolvedValueOnce('OK')

      await service.create(createDto)

      expect(repository.save).toHaveBeenCalled()
      expect(mockRedis.del).toHaveBeenCalledWith('users:list:*')
    })
  })
})
'''

# ─────────────────────────────────────────────────────────────────────────────
# NestJS Module Pattern
# ─────────────────────────────────────────────────────────────────────────────

NEST_MODULE_PATTERN = '''
import { Module } from '@nestjs/common'
import { ConfigModule, ConfigService } from '@nestjs/config'
import { TypeOrmModule } from '@nestjs/typeorm'
import { JwtModule } from '@nestjs/jwt'
import { PassportModule } from '@nestjs/passport'
import { RedisModule } from '@nestjs/redis'
import { UsersModule } from './users/users.module'
import { AuthModule } from './auth/auth.module'
import { User } from './users/user.entity'
import configuration from './config/configuration'

@Module({
  imports: [
    ConfigModule.forRoot({
      load: [configuration],
      isGlobal: true,
    }),
    TypeOrmModule.forRootAsync({
      imports: [ConfigModule],
      inject: [ConfigService],
      useFactory: (config: ConfigService) => ({
        type: 'postgres',
        host: config.get('database.host'),
        port: config.get('database.port'),
        username: config.get('database.user'),
        password: config.get('database.password'),
        database: config.get('database.name'),
        entities: [User],
        synchronize: config.get('NODE_ENV') !== 'production',  // false in prod
        logging: config.get('NODE_ENV') === 'development',
      }),
    }),
    RedisModule.forRootAsync({
      imports: [ConfigModule],
      inject: [ConfigService],
      useFactory: (config: ConfigService) => ({
        host: config.get('redis.host'),
        port: config.get('redis.port'),
      }),
    }),
    JwtModule.registerAsync({
      imports: [ConfigModule],
      inject: [ConfigService],
      useFactory: (config: ConfigService) => ({
        secret: config.get('jwt.secret'),
        signOptions: { expiresIn: config.get('jwt.expiresIn') },
      }),
    }),
    PassportModule,
    UsersModule,
    AuthModule,
  ],
  controllers: [],
  providers: [],
})
export class AppModule {}
'''

# ─────────────────────────────────────────────────────────────────────────────
# Performance Best Practices
# ─────────────────────────────────────────────────────────────────────────────

NEST_PERFORMANCE_TIPS = [
    "Use query builder for complex queries (not repository methods)",
    "Add indexes on all foreign keys and frequently filtered columns",
    "Enable second-level cache for frequently accessed, rarely changed data",
    "Use stream responses for large datasets (res.json() → res.stream())",
    "Set query timeout: `queryRunner.manager.queryTimeout = 5000`",
    "Avoid eager loading N+1: use leftJoinAndSelect selectively",
    "Use Redis caching for read-heavy endpoints (cache-aside pattern)",
    "Batch writes: save multiple entities in one transaction",
    "Use PostgreSQL COPY for bulk imports (not individual inserts)",
    "Monitor slow queries: log queries > 100ms, add pg_stat_statements",
]

# ─────────────────────────────────────────────────────────────────────────────
# Security Checklist
# ─────────────────────────────────────────────────────────────────────────────

NEST_SECURITY_CHECKLIST = [
    "✅ All routes protected by JWT auth guard where needed",
    "✅ Rate limiting on auth endpoints (5 attempts/min per IP)",
    "✅ Input validation on every DTO (class-validator)",
    "✅ SQL injection prevented (TypeORM parameterized queries)",
    "✅ CORS configured with allowlist (not wildcard)",
    "✅ Helmet middleware: app.use(helmet())",
    "✅ No hardcoded secrets — all from env vars",
    "✅ Password hashing with bcrypt (10+ rounds) or Argon2",
    "✅ Refresh tokens stored in DB (not localStorage)",
    "✅ CSRF protection on state-changing endpoints if using cookies",
]

# ─────────────────────────────────────────────────────────────────────────────
# Common Anti-Patterns to Avoid
# ─────────────────────────────────────────────────────────────────────────────

NEST_ANTIPATTERNS = {
    "god_controller": {
        "symptom": "Controller does DB queries + business logic + response formatting",
        "fix": "Move logic to service layer — controller should only validate input and call service",
    },
    "direct_db_in_service": {
        "symptom": "Service uses repository directly instead of via dependency injection",
        "fix": "Inject repository via constructor, mock in tests",
    },
    "missing_transaction": {
        "symptom": "Multiple DB writes without transaction — partial failure leaves inconsistent state",
        "fix": "Wrap in `await this.repo.manager.transaction(async (tx) => { ... })`",
    },
    "returning_raw_entity": {
        "symptom": "Controller returns ORM entity directly (exposes password hash, internal fields)",
        "fix": "Map to DTO/response object before returning",
    },
    "circular_dependency": {
        "symptom": "Service A imports Service B, Service B imports Service A",
        "fix": "Extract shared logic to third module or use forwardRef()",
    },
    "blocking_in_async": {
        "symptom": "Using sync file operations or CPU-intensive work in async route",
        "fix": "Offload to worker thread or queue, use async fs ops",
    },
}
