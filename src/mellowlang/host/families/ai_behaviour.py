"""Mellow host syscall family: ai behaviour."""

from __future__ import annotations

from ..base import HostFunction, HostRegistry


def register_ai_behaviour_functions(h: HostRegistry) -> None:
    """Register the ai behaviour syscalls on a fresh host registry."""
    # ==========================================
    # v1.4.6: AI — Steering Behaviors
    # ==========================================
    # ทุก steering รับ pos=[x,y], target=[x,y], speed=float
    # คืนค่า velocity [vx, vy] ที่ normalize แล้ว * speed

    def _vec2_normalize(vx: float, vy: float, speed: float = 1.0):
        import math as _m
        mag = _m.sqrt(vx * vx + vy * vy)
        if mag < 1e-9:
            return [0.0, 0.0]
        return [vx / mag * speed, vy / mag * speed]

    def _ai_seek(args):
        """ai_seek(pos, target, speed=1) -> [vx, vy]
        เคลื่อนที่หา target ตรงๆ
        """
        pos = args[0]
        target = args[1]
        speed = float(args[2]) if len(args) >= 3 else 1.0
        dx = float(target[0]) - float(pos[0])
        dy = float(target[1]) - float(pos[1])
        return _vec2_normalize(dx, dy, speed)

    def _ai_flee(args):
        """ai_flee(pos, threat, speed=1) -> [vx, vy]
        วิ่งหนีจาก threat
        """
        pos = args[0]
        threat = args[1]
        speed = float(args[2]) if len(args) >= 3 else 1.0
        dx = float(pos[0]) - float(threat[0])
        dy = float(pos[1]) - float(threat[1])
        return _vec2_normalize(dx, dy, speed)

    def _ai_arrive(args):
        """ai_arrive(pos, target, speed=1, slow_radius=50) -> [vx, vy]
        เคลื่อนที่หา target แล้วชะลอเมื่อใกล้ถึง
        """
        import math as _m
        pos = args[0]
        target = args[1]
        speed = float(args[2]) if len(args) >= 3 else 1.0
        slow_radius = float(args[3]) if len(args) >= 4 else 50.0
        dx = float(target[0]) - float(pos[0])
        dy = float(target[1]) - float(pos[1])
        dist = _m.sqrt(dx * dx + dy * dy)
        if dist < 1e-9:
            return [0.0, 0.0]
        effective_speed = speed * min(1.0, dist / slow_radius) if slow_radius > 0 else speed
        return [dx / dist * effective_speed, dy / dist * effective_speed]

    def _ai_wander(args):
        """ai_wander(pos, current_angle, speed=1, jitter=0.3) -> {"vel":[vx,vy], "angle":float}
        เดินเตร่แบบ deterministic (ใช้ sin/cos ของ angle ที่เปลี่ยนไปเรื่อยๆ)
        ต้องเก็บ angle ไว้ใน state แล้วส่งกลับมาทุก tick
        """
        import math as _m
        pos = args[0]
        angle = float(args[1]) if len(args) >= 2 else 0.0
        speed = float(args[2]) if len(args) >= 3 else 1.0
        jitter = float(args[3]) if len(args) >= 4 else 0.3
        # update angle (deterministic — ไม่ใช้ random)
        new_angle = angle + jitter * _m.sin(angle * 1.618)
        vx = _m.cos(new_angle) * speed
        vy = _m.sin(new_angle) * speed
        return {"vel": [vx, vy], "angle": new_angle}

    def _ai_patrol(args):
        """ai_patrol(pos, waypoints, current_idx, speed=1, threshold=5) -> {"vel":[vx,vy], "idx":int}
        순찰: เดินวนระหว่าง waypoints
        """
        import math as _m
        pos = args[0]
        waypoints = args[1]
        idx = int(args[2]) if len(args) >= 3 else 0
        speed = float(args[3]) if len(args) >= 4 else 1.0
        threshold = float(args[4]) if len(args) >= 5 else 5.0

        if not isinstance(waypoints, list) or len(waypoints) == 0:
            return {"vel": [0.0, 0.0], "idx": 0}

        idx = idx % len(waypoints)
        wp = waypoints[idx]
        dx = float(wp[0]) - float(pos[0])
        dy = float(wp[1]) - float(pos[1])
        dist = _m.sqrt(dx * dx + dy * dy)

        if dist < threshold:
            idx = (idx + 1) % len(waypoints)
            wp = waypoints[idx]
            dx = float(wp[0]) - float(pos[0])
            dy = float(wp[1]) - float(pos[1])
            dist = _m.sqrt(dx * dx + dy * dy)

        vel = _vec2_normalize(dx, dy, speed) if dist > 1e-9 else [0.0, 0.0]
        return {"vel": vel, "idx": idx}

    h.register(HostFunction('std.ai.steering.seek', _ai_seek, cost=1, min_args=2, max_args=3))
    h.register(HostFunction('std.ai.steering.flee', _ai_flee, cost=1, min_args=2, max_args=3))
    h.register(HostFunction('std.ai.steering.arrive', _ai_arrive, cost=1, min_args=2, max_args=4))
    h.register(HostFunction('std.ai.steering.wander', _ai_wander, cost=1, min_args=1, max_args=4))
    h.register(HostFunction('std.ai.steering.patrol', _ai_patrol, cost=2, min_args=3, max_args=5))

    # ==========================================
    # v1.4.6: AI — Perception
    # ==========================================

    def _ai_in_range(args):
        """ai_in_range(pos, target, radius) -> bool
        เช็คว่า target อยู่ในระยะ radius หรือไม่
        """
        import math as _m
        pos, target = args[0], args[1]
        radius = float(args[2])
        dx = float(target[0]) - float(pos[0])
        dy = float(target[1]) - float(pos[1])
        return (dx * dx + dy * dy) <= radius * radius

    def _ai_in_sight(args):
        """ai_in_sight(pos, facing_angle, target, fov_degrees=90, max_dist=200) -> bool
        เช็คว่า target อยู่ใน field of view หรือไม่
        facing_angle = องศาที่หัน (0 = ขวา, 90 = ลง)
        fov_degrees = มุมมองรวม เช่น 90 หมายถึง ±45 องศา
        """
        import math as _m
        pos = args[0]
        facing = float(args[1])
        target = args[2]
        fov = float(args[3]) if len(args) >= 4 else 90.0
        max_dist = float(args[4]) if len(args) >= 5 else 200.0

        dx = float(target[0]) - float(pos[0])
        dy = float(target[1]) - float(pos[1])
        dist = _m.sqrt(dx * dx + dy * dy)
        if dist > max_dist or dist < 1e-9:
            return False

        angle_to = _m.degrees(_m.atan2(dy, dx))
        diff = (angle_to - facing + 180) % 360 - 180
        return abs(diff) <= fov / 2.0

    def _ai_nearest(args):
        """ai_nearest(pos, targets) -> target_or_none
        หา target ที่ใกล้ที่สุดจาก list
        targets = list ของ [x, y] หรือ {"pos": [x,y], ...}
        """
        import math as _m
        pos = args[0]
        targets = args[1]
        if not isinstance(targets, list) or len(targets) == 0:
            return None

        def _get_pos(t):
            if isinstance(t, list) and len(t) >= 2:
                return t
            if isinstance(t, dict) and "pos" in t:
                return t["pos"]
            return None

        best = None
        best_dist = float('inf')
        for t in targets:
            tp = _get_pos(t)
            if tp is None:
                continue
            dx = float(tp[0]) - float(pos[0])
            dy = float(tp[1]) - float(pos[1])
            d = dx * dx + dy * dy
            if d < best_dist:
                best_dist = d
                best = t
        return best

    def _ai_filter_range(args):
        """ai_filter_range(pos, targets, radius) -> list
        กรอง targets เหลือเฉพาะที่อยู่ในระยะ radius
        """
        import math as _m
        pos = args[0]
        targets = args[1]
        radius = float(args[2])
        r2 = radius * radius

        def _get_pos(t):
            if isinstance(t, list) and len(t) >= 2:
                return t
            if isinstance(t, dict) and "pos" in t:
                return t["pos"]
            return None

        result = []
        for t in (targets or []):
            tp = _get_pos(t)
            if tp is None:
                continue
            dx = float(tp[0]) - float(pos[0])
            dy = float(tp[1]) - float(pos[1])
            if dx * dx + dy * dy <= r2:
                result.append(t)
        return result

    h.register(HostFunction('std.ai.perception.in_range', _ai_in_range, cost=1, min_args=3, max_args=3))
    h.register(HostFunction('std.ai.perception.in_sight', _ai_in_sight, cost=1, min_args=3, max_args=5))
    h.register(HostFunction('std.ai.perception.nearest', _ai_nearest, cost=2, min_args=2, max_args=2))
    h.register(HostFunction('std.ai.perception.filter_range', _ai_filter_range, cost=2, min_args=3, max_args=3))
