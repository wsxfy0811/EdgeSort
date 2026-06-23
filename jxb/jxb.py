#include <Servo.h>

/* === 硬件引脚定义 (适配 RAMPS 1.4) === */
// X轴 (底座旋转)
const int X_STEP_PIN = 54; 
const int X_DIR_PIN = 55; 
const int X_ENABLE_PIN = 38;

// Y轴 (大臂)
const int Y_STEP_PIN = 60; 
const int Y_DIR_PIN = 61; 
const int Y_ENABLE_PIN = 56;

// Z轴 (小臂)
const int Z_STEP_PIN = 46; 
const int Z_DIR_PIN = 48; 
const int Z_ENABLE_PIN = 62;

// 气动元件 (接在 RAMPS 1.4 的 Servo 引脚区)
Servo Valve; // 电磁阀 (用于破真空/放气)
Servo Pump;  // 真空泵 (用于吸气)

/* === 运动参数配置 === */
int speedDelay = 400;      // 步进电机脉冲间隔 (微秒)，数值越小速度越快，但过小可能导致电机堵转蜂鸣

// 空间运动步数 (❗需根据你机械臂的实际物理尺寸微调)
int steps_Y_down = 3000;   // 大臂下降抓取时的移动步数
int steps_Z_down = 1600;   // 小臂下降抓取时的移动步数
int steps_X_Drop = 2700;   // 底座从【检测区】旋转到【固定放置区】的移动步数
int steps_X_Defect = 2700;

void setup() {
  // 1. 初始化步进电机引脚模式
  pinMode(X_STEP_PIN, OUTPUT); pinMode(X_DIR_PIN, OUTPUT); pinMode(X_ENABLE_PIN, OUTPUT);
  pinMode(Y_STEP_PIN, OUTPUT); pinMode(Y_DIR_PIN, OUTPUT); pinMode(Y_ENABLE_PIN, OUTPUT);
  pinMode(Z_STEP_PIN, OUTPUT); pinMode(Z_DIR_PIN, OUTPUT); pinMode(Z_ENABLE_PIN, OUTPUT);

  // 2. 使能步进电机 (拉低 LOW 为开启通电，此时手应该掰不动电机轴)
  digitalWrite(X_ENABLE_PIN, LOW); 
  digitalWrite(Y_ENABLE_PIN, LOW); 
  digitalWrite(Z_ENABLE_PIN, LOW);
  
  // 3. 初始化气泵与电磁阀
  Valve.attach(11); // 左侧电磁阀接 D11
  Pump.attach(6);   // 右侧真空泵接 D6
  Valve.write(0);   // 初始状态：关闭
  Pump.write(0);    // 初始状态：关闭

  // 4. 初始化串口通信 (❗波特率必须与 Python 端设置的 115200 保持绝对一致)
  Serial.begin(115200); 
  delay(1000); // 留出充足的系统启动和稳定时间
  
  // 5. 向电脑发送初始化完成的信号
  Serial.println("READY"); 
}

// === 基础步进电机驱动函数 ===
// stepPin: 脉冲引脚 | dirPin: 方向引脚 | steps: 需要移动的总步数 | dir: 旋转方向(HIGH/LOW)
void stepMotor(int stepPin, int dirPin, int steps, bool dir) {
  digitalWrite(dirPin, dir);
  for (int i = 0; i < steps; i++) {
    digitalWrite(stepPin, HIGH);
    delayMicroseconds(speedDelay);
    digitalWrite(stepPin, LOW);
    delayMicroseconds(speedDelay);
  }
}

// === 核心流水线：定点抓取并放置 ===
void executeSorting(int target_X_steps, bool target_X_dir) {
  
  // --- 动作 1：第一阶段下降 (大臂到当前极限) ---
  Serial.println("Step 1: Big arm reaching limit (3000 steps)...");
  stepMotor(Y_STEP_PIN, Y_DIR_PIN, 3000, HIGH); 
  delay(300); // 动作切换缓冲
  
  // --- 动作 2：第二阶段调整 (小臂伸展，改变姿态) ---
  // 这里增加小臂（Z轴）的步数，调整姿态
  Serial.println("Step 2: Small arm extending...");
  stepMotor(Z_STEP_PIN, Z_DIR_PIN, 1400, LOW);  // 步数可根据实际需求微调
  delay(300);

  // --- 动作 3：第三阶段下降 (大臂继续下压 3cm 对应步数) ---
  // 3cm 大约对应 500 步左右
  Serial.println("Step 3: Big arm continues lowering 3cm...");
  stepMotor(Y_STEP_PIN, Y_DIR_PIN, 2100, HIGH); 
  delay(500); 

  // --- 动作 4：开启吸取过程 ---
  Serial.println("Action: Suction ON...");
  Valve.write(0);  
  Pump.write(180); 
  delay(3000);     // 持续吸气

  // --- 动作 5：抬起手臂 (按反序撤回) ---
  // 先把最后降下的 500 步抬起来
  stepMotor(Y_STEP_PIN, Y_DIR_PIN, 900, LOW);
  delay(200);
  // 小臂收回
  stepMotor(Z_STEP_PIN, Z_DIR_PIN, 1400, HIGH);
  delay(200);
  // 大臂回到高位 (3000 步)
  stepMotor(Y_STEP_PIN, Y_DIR_PIN, 2100, LOW);
  delay(200);

  // --- 动作 6：底座旋转搬运 ---
  stepMotor(X_STEP_PIN, X_DIR_PIN, target_X_steps, target_X_dir); 
  delay(500);

  // --- 动作 7：放置区卸载 (这里可以根据放置区高度决定是否也需要分段，暂时用普通下降) ---
  stepMotor(Y_STEP_PIN, Y_DIR_PIN, 1600, HIGH); // 降到安全高度即可
  delay(500);
  Pump.write(0);    
  Valve.write(180); 
  delay(2000);      
  Valve.write(0);   

  // --- 动作 8：抬臂并回原点 ---
  stepMotor(Y_STEP_PIN, Y_DIR_PIN, 3600, LOW); 
  delay(500);
  stepMotor(X_STEP_PIN, X_DIR_PIN, target_X_steps, !target_X_dir); 

  // 任务完成，通知电脑
  Serial.println("READY");
}

// === 主循环：监听 Python 端大脑的指令 ===
void loop() {
  if (Serial.available() > 0) {
    char cmd = Serial.read(); 
    
    if (cmd == 'N') {
      // 收到 N：正常纸板，向 HIGH 方向转动
      Serial.println("Action: Normal Cardboard confirmed.");
      executeSorting(steps_X_Drop, HIGH); 
    } 
    else if (cmd == 'D') {
      // 收到 D：缺陷纸板，向 LOW 方向转动
      Serial.println("Action: Defect detected, sorting to alternative area.");
      executeSorting(steps_X_Defect, LOW); 
    }
    
    while(Serial.available() > 0) { Serial.read(); }
  }
}
