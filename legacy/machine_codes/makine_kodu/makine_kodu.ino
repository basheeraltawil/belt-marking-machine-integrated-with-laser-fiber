int i;
int m;
int j;
int w;
int re2;
int re3;
//delaylar
int pd = 500; //stepper motor pulse time
int pnumdelay = 500; //pnumatic system delay
int fwdelay = 200; //forward delay
int bwdelay = 200; //backward delay
int dcmdelay = 200; //dcmotor delay
//STEPPER MOTOR PINS DEFINITION
const int stepPin = 48;
const int dirPin = 50;
const int enblPin = 52;
//SENSORS PINS DEFINTIOSN
int r_ls = 7; // right to left sensor pin definition
int ent_s = 11; // right to left sensor pin definition
int l_rs = 5; //left to right sensor pin definition
int ps_s = 9; //dc motor starting sensor pin definition
//PNUMATIC RELAYS AND DC MOTOR DEFINITION
int rl_r = 42; //right to left pnumatic starting relay
int lr_r = 40; //left to righ pnumatic starting relay
int mlr_r = 44; //middle pnumatic starting relay
int dcm_r = 46; //dc motor starting relay
int lasersignal = 38; //signal will be sent to laser
//SENSORS MODE
boolean rtm;   // right to left sensor mode definition
boolean lrm;   // left to right sensor mode definition
boolean psm;   // dc motor sensor mode definition
boolean ents_m;   // entrance sensor mode definition
//STEPPER MOTOR DIRECTIONS
boolean casse = HIGH;
boolean casseb = LOW;

void setup() {

  // put your setup code here, to run once:
  pinMode(r_ls, INPUT);
  pinMode(l_rs, INPUT);
  pinMode(ps_s, INPUT);
  pinMode(ent_s, INPUT);
  //OUTPUTS setting
  pinMode(mlr_r, OUTPUT);
  pinMode(lr_r, OUTPUT);
  pinMode(rl_r, OUTPUT);
  pinMode(dcm_r, OUTPUT);
  pinMode(lasersignal, OUTPUT);
  pinMode(stepPin, OUTPUT);
  pinMode(dirPin, OUTPUT);
  pinMode(enblPin, OUTPUT);
  digitalWrite(dcm_r, HIGH);
  digitalWrite(mlr_r, HIGH);
  digitalWrite(lasersignal, HIGH);
  Serial.begin(9600);


}

void loop() {
  // put your main code here, to run repeatedly:
  while (Serial.available())
  {

    String comingdata = "";
    comingdata = Serial.readString();//the erray that will be recieved from processing
    //etikit variables



    String ets  = comingdata.substring(comingdata.indexOf("a") + 1, comingdata.indexOf("b")); //etikit string value
    float tar = ets.toFloat();//etikit boytu
    //laser delay variables
    String lzs = "";
    lzs = comingdata.substring(comingdata.indexOf("b") + 1, comingdata.indexOf("c")); //delay string value
    float  laserdelay = lzs.toFloat()*1000; //delay value
    //int laserdelay = int(lzf); //lasermachine delay
    //the cuts amount

    String  etno = comingdata.substring(comingdata.indexOf("c") + 1, comingdata.indexOf("d")); //etikit numbers string
    int n = etno.toInt(); //the count of marking times
    ///gap between marking

    String gaps = comingdata.substring(comingdata.indexOf("d") + 1, comingdata.indexOf("e")); //gap string
    float gapf = gaps.toFloat(); //gap value
    float gapf1 = 69.0 * gapf;
    int gapf2 = int(gapf1);
    float metalw = 56.0; //metal gap; //METAL WIDTH FORWARD

    //FOR VALUES THAT LARGER than  METAL
    //etiket boyutu pulses 1
    float rt1 = tar;
    float rt2 = 69.0 * rt1;
    int rt3 = int(rt2);
    //metal width pulses 2
    float rm1 = 69.0 * metalw;
    int rm2 = int(rm1);
    //the diffrences for pulses 3
    int difr = (rt3) - rm2;
    //turning machine on

    String machw = comingdata.substring(comingdata.indexOf("i") + 1, comingdata.indexOf("j")); //gap string
    /////////////////////////////////////////////CUTTING
    if ( machw  == "kes")
    {
      ///FOR THOSE PIECES WHICH LARGER THAN METAL WIDTH///
      if (metalw < rt1)
      {


        for (m = 0; m < n; m++)
        {
          boolean ents_m = digitalRead(ent_s);
          if (ents_m == LOW)
          {

            if (m == 0)
            {
              digitalWrite(mlr_r, LOW);
              digitalWrite(lasersignal, LOW);
              delay(laserdelay);//LASER MACHINE RELAY MUST COME HERE
              digitalWrite(enblPin, LOW);//TURNING STEPPER MOTOR ON
              digitalWrite(dirPin,  HIGH);

              for ( i = 0; i <  rt3; i++)
              {
                digitalWrite(stepPin, HIGH);
                delayMicroseconds(pd);
                digitalWrite(stepPin, LOW);
                delayMicroseconds(pd);
                digitalWrite(mlr_r, HIGH);
                digitalWrite(dcm_r, HIGH);
                digitalWrite(lasersignal, HIGH);

              }
              delay(fwdelay);
              digitalWrite(mlr_r, LOW);
              digitalWrite(lasersignal, LOW);
              delay(laserdelay);//LASER MACHINE RELAY MUST COME HERE
              ///forward finish
            }
            //pnumatic start
            //KNIFE CUTTING ACTIONS
            if (m > 0 && m < n )
            {
              digitalWrite(enblPin, LOW);//TURNING STEPPER MOTOR ON
              digitalWrite(dirPin,  HIGH);

              for ( i = 0; i <  rm2 ; i++)
              {
                digitalWrite(stepPin, HIGH);
                delayMicroseconds(pd);
                digitalWrite(stepPin, LOW);
                delayMicroseconds(pd);
                digitalWrite(mlr_r, HIGH);
                digitalWrite(dcm_r, HIGH);
                digitalWrite(lasersignal, HIGH);

              }
              delay(fwdelay);
              
              if (m > 0 && m < n )
              delay(fwdelay);
          boolean rtm = digitalRead(r_ls);
          boolean lrm = digitalRead(l_rs);

          digitalWrite(lasersignal, HIGH);
          digitalWrite(mlr_r, HIGH);
          if (rtm == 1 && lrm == 0)
          {
            Serial.println("left to right actuator is working ");
            delay(pnumdelay);
            digitalWrite(lr_r, HIGH);
            digitalWrite(rl_r, LOW);
            delay(pnumdelay);

            digitalWrite(rl_r, HIGH);
            digitalWrite(lr_r, LOW);
            delay(pnumdelay);

          }
          if (rtm == 0 && lrm == 1)
          {
            Serial.println("right to ledft actuator is working");
            delay(pnumdelay);
            digitalWrite(lr_r, HIGH);
            digitalWrite(rl_r, LOW);
            delay(pnumdelay);
            digitalWrite(rl_r, HIGH);
            digitalWrite(lr_r, LOW);
            delay(pnumdelay);

          }
          if (rtm == 0 && lrm == 0)
          {
            Serial.println("both");
            delay(pnumdelay);
            digitalWrite(lr_r, LOW);
            digitalWrite(rl_r, HIGH);
            delay(pnumdelay);
            digitalWrite(lr_r, HIGH);
            digitalWrite(rl_r, LOW);
            delay(pnumdelay);
          }
          //pnumatic finish
              //DC MOTOR REMOVAL MECHANISM
              boolean psm = digitalRead(ps_s);
              delay(1000);
              digitalWrite(dcm_r, LOW);
              delay(1000);
              digitalWrite(dcm_r, HIGH);
              delay(1000);
              //////
              for ( i = 0; i < difr; i++)
              {
                digitalWrite(stepPin, HIGH);
                delayMicroseconds(pd);
                digitalWrite(stepPin, LOW);
                delayMicroseconds(pd);
                digitalWrite(mlr_r, HIGH);
                digitalWrite(dcm_r, HIGH);
                digitalWrite(lasersignal, HIGH);

              }
              delay(fwdelay);
              if (m > 0 && m < n-1 )
              {
              digitalWrite(mlr_r, LOW);
              digitalWrite(lasersignal, LOW);
              delay(laserdelay);//LASER MACHINE RELAY MUST COME HERE
              }

            }


          }
          if (ents_m == HIGH)
          {
            break;
          }


        }
        if (m = n )
        {
          ////
          digitalWrite(enblPin, LOW);//TURNING STEPPER MOTOR ON
          digitalWrite(dirPin,  HIGH);

          for ( i = 0; i <  rm2; i++)
          {
            digitalWrite(stepPin, HIGH);
            delayMicroseconds(pd);
            digitalWrite(stepPin, LOW);
            delayMicroseconds(pd);
            digitalWrite(mlr_r, HIGH);
            digitalWrite(dcm_r, HIGH);
            digitalWrite(lasersignal, HIGH);

          }
          delay(fwdelay);
          boolean rtm = digitalRead(r_ls);
          boolean lrm = digitalRead(l_rs);

          digitalWrite(lasersignal, HIGH);
          digitalWrite(mlr_r, HIGH);
          if (rtm == 1 && lrm == 0)
          {
            Serial.println("left to right actuator is working ");
            delay(pnumdelay);
            digitalWrite(lr_r, HIGH);
            digitalWrite(rl_r, LOW);
            delay(pnumdelay);

            digitalWrite(rl_r, HIGH);
            digitalWrite(lr_r, LOW);
            delay(pnumdelay);

          }
          if (rtm == 0 && lrm == 1)
          {
            Serial.println("right to ledft actuator is working");
            delay(pnumdelay);
            digitalWrite(lr_r, HIGH);
            digitalWrite(rl_r, LOW);
            delay(pnumdelay);
            digitalWrite(rl_r, HIGH);
            digitalWrite(lr_r, LOW);
            delay(pnumdelay);

          }
          if (rtm == 0 && lrm == 0)
          {
            Serial.println("both");
            delay(pnumdelay);
            digitalWrite(lr_r, LOW);
            digitalWrite(rl_r, HIGH);
            delay(pnumdelay);
            digitalWrite(lr_r, HIGH);
            digitalWrite(rl_r, LOW);
            delay(pnumdelay);
          }
          //pnumatic finish
          //DC MOTOR REMOVAL MECHANISM
          boolean psm = digitalRead(ps_s);
          delay(1000);
          digitalWrite(dcm_r, LOW);
          delay(1000);
          digitalWrite(dcm_r, HIGH);
          delay(1000);
          ///
          digitalWrite(enblPin, LOW);//TURNING STEPPER MOTOR ON
          digitalWrite(dirPin,  LOW);
          for ( i = 0; i <  rm2-gapf2; i++)
          {
            digitalWrite(stepPin, HIGH);
            delayMicroseconds(pd);
            digitalWrite(stepPin, LOW);
            delayMicroseconds(pd);
            digitalWrite(mlr_r, HIGH);
            digitalWrite(dcm_r, HIGH);
            digitalWrite(lasersignal, HIGH);

          }
          //
          delay(fwdelay);
          ////
          digitalWrite(mlr_r, HIGH);
          digitalWrite(lasersignal, HIGH);

          break;
        }
      }
     
    }

    /////kesmek bitti///
     /////////////////////////////////////////////NOT CUTTING
    if ( machw  == "kesm")
    {


      for (m = 0; m < n; m++)
      {
        boolean ents_m = digitalRead(ent_s);
        if (ents_m == LOW)
        {
      
          digitalWrite(mlr_r, LOW);
          digitalWrite(lasersignal, LOW);
          digitalWrite(dcm_r,HIGH);
          delay(laserdelay);//LASER MACHINE RELAY MUST COME HERE
          
          //FORWORD START
          digitalWrite(enblPin, LOW);//TURNING STEPPER MOTOR ON
          digitalWrite(dirPin,  HIGH);

          for ( i = 0; i <  rt3+gapf2 ; i++)
          {
            digitalWrite(stepPin, HIGH);
            delayMicroseconds(pd);
            digitalWrite(stepPin, LOW);
            delayMicroseconds(pd);
            digitalWrite(mlr_r, HIGH);
            digitalWrite(dcm_r, HIGH);
            digitalWrite(lasersignal, HIGH);

          }
          ///forward finish
          delay(fwdelay);
         


        }
        if (ents_m == HIGH)
        {
          break;
        }
        ////FINAL CUT
      }

      if (m = n)
      {
        delay(fwdelay);
        boolean rtm = digitalRead(r_ls);
        boolean lrm = digitalRead(l_rs);

       digitalWrite(mlr_r, LOW);
          digitalWrite(lasersignal, LOW);
          digitalWrite(dcm_r,HIGH);
          delay(laserdelay);//LASER MACHINE RELAY MUST COME HERE
          
        digitalWrite(enblPin, LOW);//TURNING STEPPER MOTOR ON
        digitalWrite(dirPin,  HIGH);

        for ( i = 0; i <  rt3+gapf2+rm2  ; i++)
          {
            digitalWrite(stepPin, HIGH);
            delayMicroseconds(pd);
            digitalWrite(stepPin, LOW);
            delayMicroseconds(pd);
            digitalWrite(mlr_r, HIGH);
            digitalWrite(dcm_r, HIGH);
            digitalWrite(lasersignal, HIGH);

          }
          delay(fwdelay);
        if (rtm == 1 && lrm == 0)
        {
          Serial.println("left to right actuator is working ");
          delay(pnumdelay);
          digitalWrite(lr_r, HIGH);
          digitalWrite(rl_r, LOW);
          delay(pnumdelay);

          digitalWrite(rl_r, HIGH);
          digitalWrite(lr_r, LOW);
          delay(pnumdelay);

        }
        if (rtm == 0 && lrm == 1)
        {
          Serial.println("right to ledft actuator is working");
          delay(pnumdelay);
          digitalWrite(lr_r, HIGH);
          digitalWrite(rl_r, LOW);
          delay(pnumdelay);
          digitalWrite(rl_r, HIGH);
          digitalWrite(lr_r, LOW);
          delay(pnumdelay);

        }
        if (rtm == 0 && lrm == 0)
        {
          Serial.println("both");
          delay(pnumdelay);
          digitalWrite(lr_r, LOW);
          digitalWrite(rl_r, HIGH);
          delay(pnumdelay);
          digitalWrite(lr_r, HIGH);
          digitalWrite(rl_r, LOW);
          delay(pnumdelay);
        }
        //pnumatic finish
        //DC MOTOR REMOVAL MECHANISM
        boolean psm = digitalRead(ps_s);
        delay(800);
        digitalWrite(dcm_r, LOW);
        delay(800);
        digitalWrite(dcm_r, HIGH);
        delay(800);
        ///
        digitalWrite(enblPin, LOW);//TURNING STEPPER MOTOR ON
        digitalWrite(dirPin,  LOW);

        for ( i = 0; i <  (rm2-gapf2)  ; i++)
          {
            digitalWrite(stepPin, HIGH);
            delayMicroseconds(pd);
            digitalWrite(stepPin, LOW);
            delayMicroseconds(pd);
            digitalWrite(mlr_r, HIGH);
            digitalWrite(dcm_r, HIGH);
            digitalWrite(lasersignal, HIGH);

          }
        ////

        break;
      }
    }
 //////BIR 
   if ( machw  == "br")
    {
        boolean ents_m = digitalRead(ent_s);
        if (ents_m == LOW)
        {
       digitalWrite(mlr_r, LOW);
       digitalWrite(lasersignal, LOW);
       digitalWrite(dcm_r,HIGH);
       delay(laserdelay);//LASER MACHINE RELAY MUST COME HERE 
       digitalWrite(enblPin, LOW);//TURNING STEPPER MOTOR ON
       digitalWrite(dirPin,  HIGH);

        for ( i = 0; i <  rt3+gapf2+rm2  ; i++)
          {
            digitalWrite(stepPin, HIGH);
            delayMicroseconds(pd);
            digitalWrite(stepPin, LOW);
            delayMicroseconds(pd);
            digitalWrite(mlr_r, HIGH);
            digitalWrite(dcm_r, HIGH);
            digitalWrite(lasersignal, HIGH);

          }
           delay(fwdelay);
           /////////////
           
          boolean rtm = digitalRead(r_ls);
          boolean lrm = digitalRead(l_rs);
          digitalWrite(lasersignal, HIGH);
          digitalWrite(mlr_r, HIGH);
          if (rtm == 1 && lrm == 0)
          {
            Serial.println("left to right actuator is working ");
            delay(pnumdelay);
            digitalWrite(lr_r, HIGH);
            digitalWrite(rl_r, LOW);
            delay(pnumdelay);
            digitalWrite(rl_r, HIGH);
            digitalWrite(lr_r, LOW);
            delay(pnumdelay);

          }
          if (rtm == 0 && lrm == 1)
          {
            Serial.println("right to ledft actuator is working");
            delay(pnumdelay);
            digitalWrite(lr_r, HIGH);
            digitalWrite(rl_r, LOW);
            delay(pnumdelay);
            digitalWrite(rl_r, HIGH);
            digitalWrite(lr_r, LOW);
            delay(pnumdelay);

          }
          if (rtm == 0 && lrm == 0)
          {
            Serial.println("both");
            delay(pnumdelay);
            digitalWrite(lr_r, LOW);
            digitalWrite(rl_r, HIGH);
            delay(pnumdelay);
            digitalWrite(lr_r, HIGH);
            digitalWrite(rl_r, LOW);
            delay(pnumdelay);
          }
          //pnumatic finish
          //DC MOTOR REMOVAL MECHANISM
          boolean psm = digitalRead(ps_s);
          delay(1000);
          digitalWrite(dcm_r, LOW);
          delay(1000);
          digitalWrite(dcm_r, HIGH);
          delay(1000);
          ///
          digitalWrite(enblPin, LOW);//TURNING STEPPER MOTOR ON
       digitalWrite(dirPin,  LOW);

        for ( i = 0; i <  rm2-gapf2  ; i++)
          {
            digitalWrite(stepPin, HIGH);
            delayMicroseconds(pd);
            digitalWrite(stepPin, LOW);
            delayMicroseconds(pd);
            digitalWrite(mlr_r, HIGH);
            digitalWrite(dcm_r, HIGH);
            digitalWrite(lasersignal, HIGH);

          }
       
        }
        break;
        }
      

    }



  }
