import asyncio
import json
import pygame
import websockets

# Initialize Pygame
pygame.init()
SCREEN_WIDTH = 800
SCREEN_HEIGHT = 600
screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption("Drone Simulation")
clock = pygame.time.Clock()

# Visual constants
DRONE_COLOR = (255, 0, 0)
PATH_COLOR = (100, 100, 255)
BACKGROUND_COLOR = (30, 30, 30)
FONT = pygame.font.SysFont('Arial', 20)
DRONE_RADIUS = 15
PATH_WIDTH = 2

# Control parameters
ALTITUDE_TOLERANCE = 0.1
COMMAND_INTERVAL = 0.3
TARGET_ALTITUDES = [3, 2]  # Alternating target altitudes
TARGET_SPEEDS = [1,1]      # Corresponding speeds for each altitude
MAX_X = 200                # Max horizontal distance used for scaling display

# Parse telemetry string into dictionary format
def parse_telemetry(telemetry_str: str) -> dict:
    try:
        parts = telemetry_str.split('-')
        return {
            'X': float(parts[1]),
            'Y': float(parts[3]),
            'BAT': float(parts[5]),
            'SENS': parts[13]
        }
    except (IndexError, ValueError, TypeError):
        return {'X': 0, 'Y': 0, 'BAT': 100}

# Main async function to run strict altitude control logic
async def strict_altitude_control():
    websocket = await websockets.connect("ws://localhost:8765")
    print("Connection established")

    current_target_idx = 0
    current_speed_idx = 0
    landing_triggered = False
    has_landed = False
    command_count = 0
    path = []               # Stores the visual path
    final_x = 0             # Final x-coordinate after landing

    try:
        # Initial command to start forward movement
        await websocket.send(json.dumps({
            "speed": TARGET_SPEEDS[current_speed_idx],
            "altitude": int(TARGET_ALTITUDES[current_target_idx]),
            "movement": "fwd"
        }))
        command_count += 1

        running = True
        while running:
            # Handle window close event
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False

            # Send landing command once battery is low
            if landing_triggered:
                await websocket.send(json.dumps({
                    "speed": 0,
                    "altitude": -1,
                    "movement": "fwd"
                }))
                command_count += 1

            # Receive and parse telemetry
            response = json.loads(await websocket.recv())
            telemetry = parse_telemetry(response.get('telemetry', ''))

            # Trigger landing if battery < 1%
            if not landing_triggered and telemetry.get('BAT', 100) < 1:
                landing_triggered = True

            # Confirm landing when altitude reaches 0
            if landing_triggered and telemetry.get('Y', 1) <= 0:
                has_landed = True
                final_x = telemetry.get('X', 0)

            # Map telemetry coordinates to screen
            x_pos = (telemetry.get('X', 0) / MAX_X) * SCREEN_WIDTH
            y_pos = SCREEN_HEIGHT / 2 - telemetry.get('Y', 0) * 20
            path.append((x_pos, y_pos))

            # Draw drone path and position
            screen.fill(BACKGROUND_COLOR)
            if len(path) >= 2:
                pygame.draw.lines(screen, PATH_COLOR, False, path, PATH_WIDTH)
            pygame.draw.circle(screen, DRONE_COLOR, (int(x_pos), int(y_pos)), DRONE_RADIUS)

            # Display telemetry or landing status
            status_text = []
            if has_landed:
                status_text.append("LANDED")
                status_text.append(f"Distance covered: {final_x:.1f}")
                status_text.append(f"Iterations: {command_count - 3}")  # Subtracting initial + landing commands
            else:
                status_text.append(f"Altitude: {telemetry.get('Y', 0):.1f}")
                status_text.append(f"X: {telemetry.get('X', 0):.1f}")

            for i, text in enumerate(status_text):
                text_surface = FONT.render(text, True, (255, 255, 255))
                screen.blit(text_surface, (10, 10 + i * 25))

            pygame.display.flip()

            # Wait before closing the window after landing
            if has_landed:
                await asyncio.sleep(3)
                running = False

            # If altitude is close enough to target, switch to next target
            if not landing_triggered:
                current_alt = telemetry.get('Y', 0)
                target_alt = TARGET_ALTITUDES[current_target_idx]
                if abs(current_alt - target_alt) <= ALTITUDE_TOLERANCE:
                    current_target_idx = (current_target_idx + 1) % len(TARGET_ALTITUDES)
                    current_speed_idx = (current_speed_idx + 1) % len(TARGET_SPEEDS)
                    alt_change = int(round(TARGET_ALTITUDES[current_target_idx] - current_alt))
                    await websocket.send(json.dumps({
                        "speed": TARGET_SPEEDS[current_speed_idx],
                        "altitude": alt_change,
                        "movement": "fwd"
                    }))
                    command_count += 1

            await asyncio.sleep(COMMAND_INTERVAL)

    except websockets.ConnectionClosed:
        pass
    finally:
        await websocket.close()
        pygame.quit()
        print("Connection severed")

# Entry point
if __name__ == "__main__":
    asyncio.run(strict_altitude_control())
