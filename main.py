"""
痛扁强强 - 狂扁小朋友风格横版动作游戏
依赖: pip install pygame
运行: python main.py
"""

import pygame
import random
import math
from enum import Enum

pygame.init()
W, H = 960, 540
screen = pygame.display.set_mode((W, H))
pygame.display.set_caption("痛扁强强")
clock = pygame.time.Clock()
FPS = 60

# 颜色
C_BG = (20, 20, 35)
C_FLOOR = (60, 60, 90)
C_HP_PLAYER = (34, 197, 94)
C_HP_ENEMY = (239, 68, 68)
C_HP_BOSS = (168, 85, 247)
C_UI_BG = (15, 15, 25, 200)
C_TEXT = (255, 255, 255)
C_COMBO = (255, 71, 71)
C_ENERGY = (168, 85, 247)

# 字体
FONT_L = pygame.font.SysFont("microsoftyahei", 36, bold=True)
FONT_M = pygame.font.SysFont("microsoftyahei", 24, bold=True)
FONT_S = pygame.font.SysFont("microsoftyahei", 18)

# ─────────────────────────────────────────────
# 向量工具
# ─────────────────────────────────────────────
def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])

def lerp(a, b, t):
    return a + (b - a) * t

def clamp(v, lo, hi):
    return max(lo, min(hi, v))

# ─────────────────────────────────────────────
# 物理常量
# ─────────────────────────────────────────────
GRAVITY = 0.65
GROUND_Y = 430
FLOOR_TOP = GROUND_Y - 5

# ─────────────────────────────────────────────
# 状态枚举
# ─────────────────────────────────────────────
class ActState(Enum):
    IDLE = 0
    WALK = 1
    JUMP = 2
    PUNCH = 3
    KICK = 4
    AIR_KICK = 5
    HURT = 6
    LAUNCHED = 7
    GROUNDED = 8
    GETUP = 9

class AIState(Enum):
    PATROL = 0
    CHASE = 1
    ATTACK = 2
    HURT = 3
    GETUP = 4

# ─────────────────────────────────────────────
# 角色基类
# ─────────────────────────────────────────────
class Fighter:
    def __init__(self, x, y, max_hp, faction="neutral"):
        self.x, self.y = x, y
        self.vx, self.vy = 0, 0
        self.w, self.h = 50, 90
        self.max_hp = max_hp
        self.hp = max_hp
        self.faction = faction  # "player", "enemy"
        self.state = ActState.IDLE
        self.facing = 1  # 1=right, -1=left
        self.on_ground = True
        self.ground_y = GROUND_Y
        self.invincible = 0
        self.stun = 0
        self.attack_cooldown = 0
        self.state_timer = 0
        self.combo = 0
        self.combo_timer = 0
        self.score = 0
        self.energy = 0
        self.hit_freeze = 0      # 击中冻结帧
        self.launched = False    # 正在空中
        self.launcher = None     # 谁击飞的
        self.landing_damage_done = False
        self.dead = False
        self.getup_timer = 0

    def get_rect(self):
        return pygame.Rect(self.x - self.w // 2, self.y - self.h, self.w, self.h)

    def flip(self, target_x):
        self.facing = 1 if target_x >= self.x else -1

    def apply_gravity(self):
        if not self.on_ground:
            self.vy += GRAVITY
            self.y += self.vy
            # 着地
            if self.y >= self.ground_y:
                self.y = self.ground_y
                vy = self.vy
                self.vy = 0
                self.on_ground = True
                # 砸地伤害
                if self.launched and vy > 10 and not self.landing_damage_done:
                    self.landing_damage_done = True
                    dmg = int(vy * 1.5)
                    if dmg > 5:
                        self.take_damage(dmg, None, is_ground=True)
                if self.launched:
                    self.launched = False
                    self.state = ActState.GROUNDED
                    self.getup_timer = 60
                return True  # 着地事件
        return False

    def take_damage(self, dmg, attacker=None, is_ground=False, launched=False):
        if self.invincible > 0:
            return
        if self.dead:
            return
        self.hp -= dmg
        if attacker:
            attacker.score += dmg
            attacker.combo += 1
            attacker.combo_timer = 120
        if self.hp <= 0:
            self.hp = 0
            self.dead = True
            if attacker:
                attacker.score += 200
        if dmg > 0:
            self.invincible = 25 if not is_ground else 35
            self.stun = 20
        if launched:
            self.launched = True
            self.on_ground = False
            self.state = ActState.LAUNCHED

    def draw_hp(self, surface, x, y, w, color, hp_ratio=None):
        if hp_ratio is None:
            hp_ratio = self.hp / self.max_hp
        # 底
        pygame.draw.rect(surface, (30, 30, 45), (x, y, w, 10), border_radius=5)
        # 条
        fill = max(0, int(w * hp_ratio))
        if fill > 0:
            pygame.draw.rect(surface, color, (x, y, fill, 10), border_radius=5)
        # 边
        pygame.draw.rect(surface, (60, 60, 80), (x, y, w, 10), 2, border_radius=5)

    def update_combo(self):
        if self.combo_timer > 0:
            self.combo_timer -= 1
        else:
            self.combo = 0

    def face_target(self, target):
        if target:
            self.facing = 1 if target.x > self.x else -1

# ─────────────────────────────────────────────
# 玩家
# ─────────────────────────────────────────────
class Player(Fighter):
    def __init__(self, x, y):
        super().__init__(x, y, 100, "player")
        self.ctrl = {
            "left": False, "right": False,
            "jump": False, "punch": False, "kick": False,
            "air_kick": False
        }
        self.anim_frame = 0
        self.anim_timer = 0
        self.input_queue = []

    def handle_input(self, events):
        just_pressed = {}
        for ev in events:
            if ev.type == pygame.KEYDOWN:
                just_pressed[ev.key] = True

        keys = pygame.key.get_pressed()
        self.ctrl["left"] = keys[pygame.K_LEFT]
        self.ctrl["right"] = keys[pygame.K_RIGHT]
        self.ctrl["jump"] = just_pressed.get(pygame.K_UP, False) or just_pressed.get(pygame.K_w, False)
        self.ctrl["punch"] = just_pressed.get(pygame.K_j, False) or just_pressed.get(pygame.K_z, False)
        self.ctrl["kick"] = just_pressed.get(pygame.K_k, False) or just_pressed.get(pygame.K_x, False)
        self.ctrl["air_kick"] = just_pressed.get(pygame.K_l, False) or just_pressed.get(pygame.K_c, False)

    def update(self):
        self.update_combo()
        if self.stun > 0:
            self.stun -= 1
            self.vx *= 0.85
        elif self.invincible > 0:
            self.invincible -= 1

        self.apply_gravity()
        self.state_timer += 1

        # ── 动画帧
        self.anim_timer += 1
        if self.anim_timer >= 8:
            self.anim_timer = 0
            self.anim_frame = (self.anim_frame + 1) % 4

        if self.hit_freeze > 0:
            self.hit_freeze -= 1
            return

        # ── 地面状态机
        if self.state not in (ActState.JUMP, ActState.LAUNCHED) and self.on_ground:
            if self.state == ActState.HURT:
                if self.stun <= 0:
                    self.state = ActState.IDLE
                return

            if self.state == ActState.GROUNDED:
                self.getup_timer -= 1
                if self.getup_timer <= 0:
                    self.state = ActState.GETUP
                    self.getup_timer = 25
                return

            if self.state == ActState.GETUP:
                if self.state_timer >= 25:
                    self.state = ActState.IDLE
                    self.state_timer = 0
                return

            if self.state in (ActState.PUNCH, ActState.KICK):
                if self.state_timer >= 18:
                    self.state = ActState.IDLE
                    self.state_timer = 0
                return

            # 攻击优先
            if self.ctrl["punch"] and self.state not in (ActState.PUNCH, ActState.KICK):
                self.state = ActState.PUNCH
                self.state_timer = 0
                self.attack_cooldown = 20
                return

            if self.ctrl["kick"] and self.state not in (ActState.PUNCH, ActState.KICK):
                self.state = ActState.KICK
                self.state_timer = 0
                self.attack_cooldown = 25
                return

            if self.ctrl["jump"] and self.on_ground:
                self.vy = -15
                self.on_ground = False
                self.state = ActState.JUMP
                return

            # 移动
            if self.ctrl["left"]:
                self.vx = -5
                if self.state not in (ActState.PUNCH, ActState.KICK):
                    self.state = ActState.WALK
            elif self.ctrl["right"]:
                self.vx = 5
                if self.state not in (ActState.PUNCH, ActState.KICK):
                    self.state = ActState.WALK
            else:
                self.vx *= 0.7
                if abs(self.vx) < 0.5:
                    self.vx = 0
                if self.state not in (ActState.PUNCH, ActState.KICK, ActState.JUMP):
                    self.state = ActState.IDLE

        # ── 跳跃状态
        elif self.state == ActState.JUMP or (not self.on_ground and self.state != ActState.LAUNCHED):
            if self.state != ActState.JUMP:
                self.state = ActState.JUMP
            # 空中踢
            if self.ctrl["air_kick"] and self.state != ActState.AIR_KICK and not self.on_ground:
                self.state = ActState.AIR_KICK
                self.state_timer = 0
                return
            if self.state == ActState.AIR_KICK:
                if self.state_timer >= 20:
                    self.state = ActState.JUMP
                    self.state_timer = 0
                return
            # 上升到位
            if self.vy >= 0 and not self.on_ground:
                self.state = ActState.JUMP

        # ── 空中攻击
        if self.state == ActState.AIR_KICK and self.on_ground:
            self.state = ActState.JUMP

        if self.attack_cooldown > 0:
            self.attack_cooldown -= 1

        # 移动
        if self.state not in (ActState.PUNCH, ActState.KICK, ActState.AIR_KICK):
            self.x += self.vx

        self.x = clamp(self.x, 30, W - 30)

    def get_attack_hitbox(self):
        if self.state == ActState.PUNCH and 4 <= self.state_timer <= 10:
            return pygame.Rect(
                self.x + self.facing * 20,
                self.y - 60, 55, 40
            )
        if self.state == ActState.KICK and 5 <= self.state_timer <= 12:
            return pygame.Rect(
                self.x + self.facing * 15,
                self.y - 30, 60, 35
            )
        if self.state == ActState.AIR_KICK and 4 <= self.state_timer <= 14:
            return pygame.Rect(
                self.x + self.facing * 10,
                self.y - 50, 65, 50
            )
        return None

    def get_attack_dmg(self):
        b = 8 + random.randint(0, 5)
        if self.combo >= 5:
            b = int(b * 1.5)
        if self.combo >= 10:
            b = int(b * 2.0)
        if self.state == ActState.AIR_KICK:
            b = int(b * 1.4)
        return b

    def draw(self, surface):
        # 受伤闪烁
        if self.invincible > 0 and (self.invincible // 4) % 2 == 0:
            return

        cx = int(self.x)
        cy = int(self.y)

        # 影子
        if not self.on_ground:
            shadow_s = int(30 * (1 - (GROUND_Y - self.y) / 200))
            shadow_s = max(10, shadow_s)
            pygame.draw.ellipse(surface, (0,0,0,80), (cx - shadow_s, GROUND_Y - 2, shadow_s * 2, 8))

        # 身体颜色（玩家用吴彦祖）
        body_color = (80, 160, 255)
        skin = (255, 210, 170)

        # 站立/走路帧
        bob_y = 0
        if self.state == ActState.WALK:
            bob_y = abs(math.sin(self.anim_frame * math.pi / 2)) * 4

        # ── 身体
        # 头发/头
        pygame.draw.ellipse(surface, (40, 30, 20), (cx - 16, cy - 88 - bob_y, 32, 32))
        pygame.draw.ellipse(surface, skin, (cx - 13, cy - 84 - bob_y, 26, 26))

        # 身体
        pygame.draw.rect(surface, body_color, (cx - 18, cy - 60 - bob_y, 36, 35))

        # 手臂
        arm_color = skin
        if self.state == ActState.PUNCH:
            if self.state_timer < 10:
                punch_x = cx + self.facing * (25 + self.state_timer * 4)
                punch_y = cy - 55 - bob_y
                pygame.draw.line(surface, arm_color, (cx + self.facing * 12, cy - 55 - bob_y), (punch_x, punch_y), 8)
                pygame.draw.circle(surface, arm_color, (int(punch_x), int(punch_y)), 6)
            else:
                pygame.draw.line(surface, arm_color, (cx - 10, cy - 55 - bob_y), (cx - 22, cy - 40 - bob_y), 7)
                pygame.draw.line(surface, arm_color, (cx + 10, cy - 55 - bob_y), (cx + 24, cy - 45 - bob_y), 7)
        elif self.state == ActState.KICK:
            pygame.draw.line(surface, arm_color, (cx - 10, cy - 55 - bob_y), (cx - 20, cy - 40 - bob_y), 7)
            pygame.draw.line(surface, arm_color, (cx + 10, cy - 55 - bob_y), (cx + 20, cy - 40 - bob_y), 7)
        else:
            pygame.draw.line(surface, arm_color, (cx - 12, cy - 58 - bob_y), (cx - 24, cy - 38 - bob_y), 7)
            pygame.draw.line(surface, arm_color, (cx + 12, cy - 58 - bob_y), (cx + 24, cy - 38 - bob_y), 7)

        # 腿
        leg_color = (40, 40, 80)
        if self.state == ActState.KICK and 5 <= self.state_timer <= 14:
            kx = cx + self.facing * (20 + self.state_timer * 4)
            ky = cy - 10
            pygame.draw.line(surface, leg_color, (cx, cy - 28 - bob_y), (int(kx), int(ky)), 10)
            pygame.draw.circle(surface, (60, 60, 100), (int(kx), int(ky)), 8)
        elif self.state == ActState.AIR_KICK and 4 <= self.state_timer <= 16:
            kx = cx + self.facing * (25 + self.state_timer * 5)
            ky = cy - 25 + self.state_timer
            pygame.draw.line(surface, leg_color, (cx, cy - 28), (int(kx), int(ky)), 12)
            pygame.draw.circle(surface, (60, 60, 100), (int(kx), int(ky)), 10)
        elif self.state == ActState.JUMP or not self.on_ground:
            pygame.draw.line(surface, leg_color, (cx - 10, cy - 28), (cx - 15, cy - 5), 9)
            pygame.draw.line(surface, leg_color, (cx + 10, cy - 28), (cx + 15, cy - 5), 9)
        else:
            l1 = math.sin(self.anim_frame * math.pi / 2) * 5 if self.state == ActState.WALK else 0
            l2 = -l1
            pygame.draw.line(surface, leg_color, (cx - 8, cy - 28), (cx - 10 + int(l1), cy), 9)
            pygame.draw.line(surface, leg_color, (cx + 8, cy - 28), (cx + 10 + int(l2), cy), 9)

        # 攻击特效
        if self.state == ActState.PUNCH and 4 <= self.state_timer <= 10:
            fx = cx + self.facing * (50 + self.state_timer * 5)
            fy = cy - 55 - bob_y
            pygame.draw.circle(surface, (255, 200, 50), (int(fx), int(fy)), 12, 3)
        if self.state == ActState.KICK and 5 <= self.state_timer <= 14:
            fx = cx + self.facing * (50 + self.state_timer * 6)
            fy = cy - 10
            pygame.draw.circle(surface, (255, 100, 50), (int(fx), int(fy)), 15, 3)
        if self.state == ActState.AIR_KICK and 4 <= self.state_timer <= 16:
            fx = cx + self.facing * (55 + self.state_timer * 7)
            fy = cy - 25 + self.state_timer
            pygame.draw.circle(surface, (255, 50, 50), (int(fx), int(fy)), 18, 4)

# ─────────────────────────────────────────────
# 强强敌人
# ─────────────────────────────────────────────
class Kid(Fighter):
    def __init__(self, x, y, wave=1, boss=False):
        super().__init__(x, y, 80 if not boss else 200, "enemy")
        self.wave = wave
        self.boss = boss
        self.max_hp = 80 if not boss else 200
        self.hp = self.max_hp
        self.state = ActState.IDLE
        self.ai_state = AIState.PATROL
        self.ai_timer = 0
        self.patrol_dir = random.choice([-1, 1])
        self.patrol_timer = random.randint(60, 120)
        self.attack_timer = 0
        self.dead = False
        self.anim_frame = 0
        self.anim_timer = 0

    def update(self, target=None):
        if self.dead:
            return
        self.update_combo()
        if self.stun > 0:
            self.stun -= 1
            self.vx *= 0.85
        if self.invincible > 0:
            self.invincible -= 1

        self.apply_gravity()
        self.state_timer += 1
        self.ai_timer += 1

        self.anim_timer += 1
        if self.anim_timer >= 10:
            self.anim_timer = 0
            self.anim_frame = (self.anim_frame + 1) % 4

        if self.hit_freeze > 0:
            self.hit_freeze -= 1
            return

        # ── 倒地起身
        if self.state == ActState.GROUNDED:
            self.getup_timer -= 1
            if self.getup_timer <= 0:
                self.state = ActState.GETUP
                self.state_timer = 0
            return

        if self.state == ActState.GETUP:
            if self.state_timer >= 30:
                self.state = ActState.IDLE
                self.state_timer = 0
                self.ai_state = AIState.PATROL
            return

        # 被击飞状态
        if self.state == ActState.LAUNCHED:
            self.x += self.vx
            self.vx *= 0.96
            return

        if self.state == ActState.HURT:
            if self.stun <= 0:
                self.state = ActState.IDLE
            return

        if not target:
            # 巡逻
            if self.state in (ActState.IDLE, ActState.WALK):
                self.patrol_timer -= 1
                if self.patrol_timer <= 0:
                    self.patrol_dir *= -1
                    self.patrol_timer = random.randint(80, 160)
                self.vx = self.patrol_dir * 1.5
                self.x += self.vx
                if self.x < 80:
                    self.patrol_dir = 1
                elif self.x > W - 80:
                    self.patrol_dir = -1
                self.state = ActState.WALK if self.patrol_dir != 0 else ActState.IDLE
            return

        # ── AI攻击状态
        d = dist((self.x, self.y), (target.x, target.y))
        self.flip(target.x)

        if self.state == ActState.PUNCH or self.state == ActState.KICK:
            if self.state_timer >= 22:
                self.state = ActState.IDLE
                self.attack_timer = 50 + random.randint(0, 60)
            return

        if self.attack_timer > 0:
            self.attack_timer -= 1

        # ── 追击距离
        if d < 60 and self.attack_timer <= 0:
            # 近身攻击
            self.state = ActState.PUNCH
            self.state_timer = 0
            self.attack_timer = 60 + random.randint(0, 60)
            return

        # ── 追击
        if d < 350:
            self.ai_state = AIState.CHASE
            speed = 2.0 + self.wave * 0.3
            if self.boss:
                speed *= 1.3
            self.vx = self.facing * speed
            self.x += self.vx
            self.state = ActState.WALK
        else:
            # 巡逻
            self.ai_state = AIState.PATROL
            self.patrol_timer -= 1
            if self.patrol_timer <= 0:
                self.patrol_dir *= -1
                self.patrol_timer = random.randint(80, 160)
            self.vx = self.patrol_dir * 1.2
            self.x += self.vx
            self.state = ActState.WALK
            if self.x < 80:
                self.patrol_dir = 1
            elif self.x > W - 80:
                self.patrol_dir = -1

        self.x = clamp(self.x, 30, W - 30)

    def get_attack_hitbox(self):
        if self.state == ActState.PUNCH and 5 <= self.state_timer <= 12:
            return pygame.Rect(
                self.x + self.facing * 15,
                self.y - 65, 50, 40
            )
        return None

    def get_attack_dmg(self):
        return 5 + self.wave * 2 + random.randint(0, 4)

    def take_damage(self, dmg, attacker=None, is_ground=False, launched=False):
        if self.invincible > 0 and not launched:
            return
        super().take_damage(dmg, attacker, is_ground, launched)
        if launched:
            self.launched = True
            self.on_ground = False
            self.state = ActState.LAUNCHED
            self.vx = (attacker.x - self.x) * 0.4 + (1 if attacker.x < self.x else -1) * 5
            self.vy = -10
            self.stun = 30

    def die(self):
        self.dead = True
        self.state = ActState.GROUNDED
        self.getup_timer = 9999

    def draw(self, surface):
        if self.dead and self.state_timer > 9998:
            return

        cx = int(self.x)
        cy = int(self.y)

        # 受伤闪烁
        if self.invincible > 0 and (self.invincible // 4) % 2 == 0:
            return

        # 阴影
        shadow_s = 28
        if not self.on_ground:
            shadow_s = max(8, int(28 * (1 - abs(GROUND_Y - self.y) / 250)))
        pygame.draw.ellipse(surface, (0, 0, 0, 90), (cx - shadow_s, GROUND_Y - 2, shadow_s * 2, 8))

        bob_y = 0
        if self.state == ActState.WALK:
            bob_y = abs(math.sin(self.anim_frame * math.pi / 2)) * 3

        # ── 强强配色
        body = (100, 150, 255)
        shirt = (255, 80, 80)
        skin = (255, 220, 180)

        if self.boss:
            body = (180, 50, 50)
            shirt = (80, 40, 200)

        # 头
        head_y = cy - 85 - bob_y
        pygame.draw.ellipse(surface, skin, (cx - 15, head_y, 30, 28))
        # 头发乱
        pygame.draw.ellipse(surface, (30, 20, 20), (cx - 16, head_y - 4, 32, 18))
        # 愤怒眉毛
        pygame.draw.line(surface, (40, 0, 0), (cx - 10, head_y + 6), (cx - 4, head_y + 8), 2)
        pygame.draw.line(surface, (40, 0, 0), (cx + 10, head_y + 6), (cx + 4, head_y + 8), 2)
        pygame.draw.ellipse(surface, (20, 0, 0), (cx - 7, head_y + 10, 5, 5))
        pygame.draw.ellipse(surface, (20, 0, 0), (cx + 2, head_y + 10, 5, 5))

        # 身体
        pygame.draw.rect(surface, shirt, (cx - 16, cy - 58 - bob_y, 32, 32))

        # 手臂
        if self.state == ActState.PUNCH and 5 <= self.state_timer <= 12:
            ex = cx + self.facing * (20 + self.state_timer * 4)
            ey = cy - 52 - bob_y
            pygame.draw.line(surface, skin, (cx + self.facing * 10, cy - 52 - bob_y), (int(ex), int(ey)), 7)
            pygame.draw.circle(surface, skin, (int(ex), int(ey)), 6)
        else:
            pygame.draw.line(surface, skin, (cx - 10, cy - 55 - bob_y), (cx - 22, cy - 35 - bob_y), 6)
            pygame.draw.line(surface, skin, (cx + 10, cy - 55 - bob_y), (cx + 22, cy - 35 - bob_y), 6)

        # 腿
        pant = (30, 30, 120) if not self.boss else (50, 20, 100)
        if self.state == ActState.WALK:
            l1 = math.sin(self.anim_frame * math.pi / 2) * 4
            pygame.draw.line(surface, pant, (cx - 7, cy - 26), (cx - 9 + int(l1), cy), 8)
            pygame.draw.line(surface, pant, (cx + 7, cy - 26), (cx + 9 - int(l1), cy), 8)
        else:
            pygame.draw.line(surface, pant, (cx - 7, cy - 26), (cx - 9, cy), 8)
            pygame.draw.line(surface, pant, (cx + 7, cy - 26), (cx + 9, cy), 8)

        # BOSS光环
        if self.boss:
            # 血条全红背景
            pass

    def draw_health_bar(self, surface):
        cx = int(self.x)
        y = self.y - self.h - 15
        w = 60 if not self.boss else 90
        self.draw_hp(surface, cx - w // 2, y, w, C_HP_BOSS if self.boss else C_HP_ENEMY)
        # 名字
        name = "BOSS强强" if self.boss else "小强强"
        txt = FONT_S.render(name, True, C_TEXT)
        surface.blit(txt, (cx - txt.get_width() // 2, y - 18))

# ─────────────────────────────────────────────
# 可交互物品
# ─────────────────────────────────────────────
class Prop:
    def __init__(self, x, y, kind="trashcan"):
        self.x, self.y = x, y
        self.kind = kind
        self.destroyed = False
        self.bounce_vx = 0
        self.bounce_vy = 0
        self.bounce_y = y
        self.bounce_timer = 0
        self.hit_flash = 0

        if kind == "trashcan":
            self.w, self.h = 40, 55
            self.color = (150, 150, 160)
        elif kind == "sign":
            self.w, self.h = 30, 70
            self.color = (100, 80, 60)
        else:
            self.w, self.h = 50, 50
            self.color = (120, 100, 80)

    def update(self):
        if self.bounce_timer > 0:
            self.bounce_timer -= 1
            self.bounce_y += self.bounce_vy
            self.bounce_vy += 0.5
            if self.bounce_y >= self.y:
                self.bounce_y = self.y
                self.bounce_vy = 0

    def draw(self, surface):
        if self.destroyed:
            # 碎片
            for i in range(4):
                fx = self.x - 15 + i * 12
                fy = self.y - 10 - i * 5 + math.sin(self.bounce_timer * 0.2 + i) * 5
                if self.bounce_timer < 30 + i * 5:
                    pygame.draw.rect(surface, self.color, (int(fx), int(fy), 8, 8))
            return
        if self.hit_flash > 0:
            self.hit_flash -= 1
        cx = int(self.x)
        cy = int(self.bounce_y)
        if self.kind == "trashcan":
            pygame.draw.rect(surface, (120, 120, 130), (cx - 18, cy - 50, 36, 50))
            pygame.draw.ellipse(surface, (100, 100, 110), (cx - 20, cy - 55, 40, 15))
            pygame.draw.rect(surface, (90, 90, 100), (cx - 5, cy - 55, 10, 8))
        elif self.kind == "sign":
            pygame.draw.rect(surface, (80, 60, 40), (cx - 4, cy - 65, 8, 65))
            pygame.draw.rect(surface, (180, 140, 80), (cx - 22, cy - 65, 44, 30), border_radius=4)
        else:
            pygame.draw.rect(surface, self.color, (cx - 22, cy - 45, 44, 45), border_radius=4)

    def hit(self, attacker):
        if self.destroyed:
            return 0
        self.destroyed = True
        self.bounce_vy = -8
        self.bounce_timer = 40
        # 击中反馈
        self.hit_flash = 10
        return 15

# ─────────────────────────────────────────────
# 伤害数字
# ─────────────────────────────────────────────
class DamageText:
    def __init__(self, x, y, text, color=(255, 220, 60)):
        self.x, self.y = x
        self.text = text
        self.color = color
        self.vy = -3
        self.life = 50
        self.scale = 1.5

    def update(self):
        self.y += self.vy
        self.vy += 0.05
        self.life -= 1
        self.scale = max(0.6, self.scale - 0.04)

    def draw(self, surface):
        alpha = min(255, self.life * 8)
        size = int(24 * self.scale)
        font = pygame.font.SysFont("microsoftyahei", size, bold=True)
        img = font.render(self.text, True, self.color)
        img.set_alpha(alpha)
        surface.blit(img, (int(self.x - img.get_width() // 2), int(self.y)))

# ─────────────────────────────────────────────
# 游戏主类
# ─────────────────────────────────────────────
class Game:
    def __init__(self):
        self.running = True
        self.state = "start"  # start, playing, wave_clear, game_over, win
        self.wave = 1
        self.max_waves = 4
        self.player = Player(150, GROUND_Y)
        self.enemies = []
        self.props = []
        self.damage_texts = []
        self.particles = []
        self.wave_banner_timer = 0
        self.wave_banner_text = ""
        self.ko_timer = 0
        self.wave_clear_timer = 0
        self.screen_shake = 0
        self.start_timer = 0
        self._spawn_wave(1)

    def _spawn_wave(self, wave_num):
        self.enemies = []
        self.props = []
        self.wave = wave_num

        # 场景物品
        positions = [(200, GROUND_Y), (450, GROUND_Y), (700, GROUND_Y), (850, GROUND_Y)]
        kinds = ["trashcan", "sign", "trashcan", "sign"]
        random.shuffle(positions)
        for i in range(min(wave_num + 1, 4)):
            p = Prop(positions[i][0], positions[i][1], kinds[i])
            self.props.append(p)

        # 敌人
        if wave_num < self.max_waves:
            count = wave_num + 1
        else:
            count = 1  # BOSS

        for i in range(count):
            ex = random.randint(500, 850)
            ey = GROUND_Y
            boss = (wave_num == self.max_waves and i == 0)
            kid = Kid(ex, ey, wave_num, boss)
            self.enemies.append(kid)

        # 玩家重置位置
        self.player.x = 120
        self.player.y = GROUND_Y
        self.player.hp = self.player.max_hp
        self.player.state = ActState.IDLE
        self.player.launched = False
        self.player.on_ground = True
        self.player.combo = 0

        self.wave_banner_text = f"第 {wave_num} 波" if wave_num < self.max_waves else "BOSS战!"
        self.wave_banner_timer = 150

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.running = False
                if self.state == "start" and event.key == pygame.K_RETURN:
                    self.state = "playing"
                elif self.state in ("game_over", "win") and event.key == pygame.K_r:
                    self.__init__()

        if self.state == "playing":
            self.player.handle_input(pygame.event.get())

    def _do_attack(self, attacker, enemies, props, is_player=True):
        hb = attacker.get_attack_hitbox()
        if not hb:
            return
        hit = False

        for e in enemies:
            if e.dead:
                continue
            if hb.colliderect(e.get_rect()):
                if e.hit_freeze > 0:
                    continue
                dmg = attacker.get_attack_dmg()
                e.take_damage(dmg, attacker, launched=True)
                e.hit_freeze = 12
                e.state = ActState.HURT
                e.state_timer = 0
                e.stun = 20

                # 击飞方向
                direction = 1 if attacker.x < e.x else -1
                knockback = dmg * 0.7 + 4
                e.vx = direction * knockback
                e.vy = -8 - dmg * 0.3
                e.on_ground = False
                e.launched = True

                # 击中冻结
                attacker.hit_freeze = 6
                if is_player:
                    self.screen_shake = 5
                    self.player.energy = min(100, self.player.energy + 10)
                # 伤害文字
                color = (255, 60, 60) if dmg >= 20 else (255, 220, 60)
                self.damage_texts.append(DamageText(e.x, e.y - 60, str(dmg), color))
                # 粒子
                self._spawn_hit_particles(e.x, e.y - 50, direction)
                hit = True

                if e.hp <= 0:
                    e.die()
                    if is_player:
                        self.player.score += 200
                break  # 一拳只打一个

        # 道具
        for prop in props:
            if prop.destroyed:
                continue
            if hb.colliderect(pygame.Rect(prop.x - prop.w // 2, prop.y - prop.h, prop.w, prop.h)):
                prop.hit(attacker)
                self.damage_texts.append(DamageText(prop.x, prop.y - 50, "+15", (150, 255, 150)))
                self.screen_shake = 3

        return hit

    def _spawn_hit_particles(self, x, y, direction):
        for _ in range(6):
            self.particles.append({
                "x": x + random.randint(-10, 10),
                "y": y + random.randint(-10, 10),
                "vx": direction * random.uniform(2, 6),
                "vy": random.uniform(-4, -1),
                "life": 20 + random.randint(0, 15),
                "color": random.choice([(255, 200, 50), (255, 100, 50), (255, 255, 100)])
            })

    def _check_player_hit(self, enemy):
        if enemy.dead:
            return
        hb = enemy.get_attack_hitbox()
        if not hb:
            return
        if hb.colliderect(self.player.get_rect()):
            if self.player.invincible > 0:
                return
            dmg = enemy.get_attack_dmg()
            self.player.take_damage(dmg, None)
            self.player.stun = 15
            self.screen_shake = 8
            # 击退
            dir = 1 if enemy.x < self.player.x else -1
            self.player.vx = dir * 6
            self.damage_texts.append(DamageText(self.player.x, self.player.y - 60, str(dmg), (100, 255, 100)))
            self.screen_shake = 6

    def update(self):
        if self.state == "start":
            self.start_timer += 1
            return
        if self.state == "wave_clear":
            self.wave_clear_timer -= 1
            if self.wave_clear_timer <= 0:
                if self.wave < self.max_waves:
                    self._spawn_wave(self.wave + 1)
                    self.state = "playing"
                else:
                    self.state = "win"
            return
        if self.state in ("game_over", "win"):
            return

        # 波次横幅
        if self.wave_banner_timer > 0:
            self.wave_banner_timer -= 1

        # K.O. 计时
        if self.ko_timer > 0:
            self.ko_timer -= 1

        # 屏幕震动
        if self.screen_shake > 0:
            self.screen_shake -= 1

        # 更新粒子
        self.particles = [p for p in self.particles if p["life"] > 0]
        for p in self.particles:
            p["x"] += p["vx"]
            p["y"] += p["vy"]
            p["vy"] += 0.3
            p["life"] -= 1

        # 更新伤害文字
        self.damage_texts = [d for d in self.damage_texts if d.life > 0]
        for d in self.damage_texts:
            d.update()

        # 更新道具
        for prop in self.props:
            prop.update()

        # 更新玩家
        self.player.update()

        # 玩家攻击检测
        if self.player.state in (ActState.PUNCH, ActState.KICK, ActState.AIR_KICK):
            self._do_attack(self.player, self.enemies, self.props, True)

        # 检查所有敌人死亡
        alive = [e for e in self.enemies if not e.dead]
        if len(alive) == 0 and self.state == "playing":
            self.wave_clear_timer = 120
            self.ko_timer = 90
            self.state = "wave_clear"
            return

        # 更新敌人AI
        for e in self.enemies:
            if not e.dead:
                e.update(self.player)

        # 敌人攻击检测
        for e in self.enemies:
            if not e.dead:
                self._check_player_hit(e)

        # 玩家死亡
        if self.player.hp <= 0:
            self.state = "game_over"

    def draw_bg(self, surface):
        surface.fill(C_BG)
        # 城市剪影
        pygame.draw.rect(surface, (15, 15, 28), (0, 300, W, 140))
        for bx in range(0, W, 120):
            bh = 80 + (bx // 37) % 80
            pygame.draw.rect(surface, (18, 18, 35), (bx + 20, 430 - bh, 80, bh))
            # 窗户
            for wy in range(430 - bh + 10, 425, 20):
                for wx in range(bx + 28, bx + 90, 18):
                    if random.random() > 0.4:
                        pygame.draw.rect(surface, (255, 240, 150), (wx, wy, 8, 10))
        # 地板
        pygame.draw.rect(surface, C_FLOOR, (0, FLOOR_TOP, W, H - FLOOR_TOP))
        pygame.draw.line(surface, (80, 80, 120), (0, FLOOR_TOP), (W, FLOOR_TOP), 2)

    def draw_ui(self, surface):
        # 玩家血条
        pygame.draw.rect(surface, (10, 10, 20), (15, 12, 220, 50), border_radius=10)
        pygame.draw.rect(surface, (30, 30, 50), (15, 12, 220, 50), 2, border_radius=10)
        txt = FONT_S.render("吴彦祖", True, (180, 180, 200))
        surface.blit(txt, (20, 16))
        # HP条
        hp_r = self.player.hp / self.player.max_hp
        fill_w = int(200 * hp_r)
        if fill_w > 0:
            pygame.draw.rect(surface, C_HP_PLAYER, (20, 32, fill_w, 14), border_radius=7)
        pygame.draw.rect(surface, (40, 40, 60), (20, 32, 200, 14), 2, border_radius=7)

        # 能量条
        pygame.draw.rect(surface, (20, 20, 35), (20, 50, 200, 10), border_radius=5)
        ef = int(200 * self.player.energy / 100)
        if ef > 0:
            pygame.draw.rect(surface, C_ENERGY, (20, 50, ef, 10), border_radius=5)
        pygame.draw.rect(surface, (50, 50, 80), (20, 50, 200, 10), 1, border_radius=5)
        energy_txt = FONT_S.render(f"能量 {self.player.energy}%", True, C_ENERGY)
        surface.blit(energy_txt, (225, 47))

        # 分数
        score_txt = FONT_M.render(f"分数 {self.player.score}", True, (200, 200, 200))
        surface.blit(score_txt, (W - 160, 15))

        # 连击
        if self.player.combo >= 3:
            combo_color = (255, 71, 71) if self.player.combo < 10 else (255, 50, 50)
            cs = min(36, 24 + self.player.combo * 2)
            combo_font = pygame.font.SysFont("microsoftyahei", cs, bold=True)
            c_txt = combo_font.render(f"{self.player.combo} 连击!", True, combo_color)
            surface.blit(c_txt, (W // 2 - c_txt.get_width() // 2, 15))
            pulse = abs(math.sin(pygame.time.get_ticks() * 0.015)) * 0.1 + 1
            # 额外放大效果
            if self.player.combo >= 10:
                glow = FONT_S.render(f"暴击倍率 {min(3, 1 + self.player.combo * 0.1):.1f}x", True, (255, 200, 50))
                surface.blit(glow, (W // 2 - glow.get_width() // 2, 50))

        # 波次
        wave_txt = FONT_S.render(f"第 {self.wave}/{self.max_waves} 波", True, (150, 150, 150))
        surface.blit(wave_txt, (W // 2 - wave_txt.get_width() // 2, H - 25))

    def draw_wave_banner(self, surface):
        if self.wave_banner_timer > 0:
            alpha = min(255, self.wave_banner_timer * 8)
            size = 42 + int((150 - self.wave_banner_timer) * 0.1)
            size = max(30, min(50, size))
            f = pygame.font.SysFont("microsoftyahei", size, bold=True)
            color = C_HP_BOSS if self.wave == self.max_waves else (255, 220, 60)
            txt = f.render(self.wave_banner_text, True, color)
            txt.set_alpha(alpha)
            # 阴影
            shad = f.render(self.wave_banner_text, True, (0, 0, 0))
            shad.set_alpha(alpha // 2)
            surface.blit(shad, (W // 2 - txt.get_width() // 2 + 3, H // 2 - 50 + 3))
            surface.blit(txt, (W // 2 - txt.get_width() // 2, H // 2 - 50))

    def draw_ko(self, surface):
        if self.ko_timer > 0:
            alpha = min(255, self.ko_timer * 6)
            size = int(80 + (90 - self.ko_timer) * 0.8)
            size = max(50, min(100, size))
            f = pygame.font.SysFont("microsoftyahei", size, bold=True, italic=True)
            txt = f.render("K.O.", True, (255, 30, 30))
            txt.set_alpha(alpha)
            # 发光
            glow = f.render("K.O.", True, (255, 100, 100))
            glow.set_alpha(alpha // 3)
            surface.blit(glow, (W // 2 - txt.get_width() // 2 - 4, H // 2 - 60 - 4))
            surface.blit(txt, (W // 2 - txt.get_width() // 2, H // 2 - 60))

    def draw_start_screen(self, surface):
        surface.fill((10, 10, 20))
        title = FONT_L.render("痛扁强强", True, (255, 70, 70))
        surface.blit(title, (W // 2 - title.get_width() // 2, 120))
        sub = FONT_M.render("痛扁小朋友风格横版动作游戏", True, (100, 100, 120))
        surface.blit(sub, (W // 2 - sub.get_width() // 2, 170))
        # 操作说明
        ops = [
            "移动: ← → 或 A D",
            "跳跃: ↑ 或 W",
            "出拳: J 或 Z",
            "踢腿: K 或 X",
            "空中踢: L 或 C (跳跃中)",
            "",
            "按 ENTER 开始游戏"
        ]
        for i, line in enumerate(ops):
            fc = (200, 200, 200) if i < len(ops) - 1 else (255, 220, 60)
            f = FONT_S if i < len(ops) - 1 else FONT_M
            t = f.render(line, True, fc)
            surface.blit(t, (W // 2 - t.get_width() // 2, 230 + i * 30))

    def draw_end_screen(self, surface):
        surface.fill((10, 10, 20))
        if self.state == "win":
            t = FONT_L.render("胜利! 强强被痛扁了!", True, (74, 222, 128))
            sub = FONT_M.render(f"最终得分: {self.player.score}", True, (255, 220, 60))
        else:
            t = FONT_L.render("K.O. 你被打趴了", True, (255, 71, 71))
            sub = FONT_M.render(f"得分: {self.player.score}", True, (150, 150, 150))
        surface.blit(t, (W // 2 - t.get_width() // 2, 160))
        surface.blit(sub, (W // 2 - sub.get_width() // 2, 210))
        hint = FONT_S.render("按 R 重新开始", True, (100, 100, 120))
        surface.blit(hint, (W // 2 - hint.get_width() // 2, 280))

    def draw(self, surface):
        if self.state == "start":
            self.draw_start_screen(surface)
            return

        if self.state in ("game_over", "win"):
            self.draw_end_screen(surface)
            return

        # 背景
        self.draw_bg(surface)

        # 屏幕震动
        ox, oy = 0, 0
        if self.screen_shake > 0:
            ox = random.randint(-4, 4)
            oy = random.randint(-3, 3)

        # 道具
        for prop in self.props:
            prop.draw(surface)

        # 玩家
        self.player.draw(surface)

        # 敌人
        for e in self.enemies:
            e.draw(surface)
            e.draw_health_bar(surface)

        # 粒子
        for p in self.particles:
            alpha = min(255, p["life"] * 12)
            size = max(2, int(6 * p["life"] / 35))
            pygame.draw.circle(surface, p["color"], (int(p["x"]), int(p["y"])), size)

        # 伤害文字
        for d in self.damage_texts:
            d.draw(surface)

        # UI
        self.draw_ui(surface)

        # 波次横幅
        self.draw_wave_banner(surface)

        # K.O.
        self.draw_ko(surface)

    def run(self):
        while self.running:
            self.handle_events()
            self.update()
            self.draw(screen)
            pygame.display.flip()
            clock.tick(FPS)

        pygame.quit()

if __name__ == "__main__":
    Game().run()