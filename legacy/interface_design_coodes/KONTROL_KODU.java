import processing.core.*; 
import processing.data.*; 
import processing.event.*; 
import processing.opengl.*; 

import controlP5.*; 
import processing.serial.*; 

import java.util.HashMap; 
import java.util.ArrayList; 
import java.io.File; 
import java.io.BufferedReader; 
import java.io.PrintWriter; 
import java.io.InputStream; 
import java.io.OutputStream; 
import java.io.IOException; 

public class KONTROL_KODU extends PApplet {



Serial port;
ControlP5 cp5;
boolean isRotating = true; 
int counterForRotation=0; 
int c = color(255, 100, 30);
// circle center 
float x1=650;
float y1=550;
// that is added to the angle
float pos=1;
float x = 0;
float y = 530;
float speed =5;
PFont font;
String text1="";
String text2="";
String text3="";
String text4="";
String text6;
String tottext;
String [] ttext;
PImage img;
PImage img1;
PImage img2;
PImage img3;
PImage img4;
PImage img5;
public void setup()
{
  
  img=loadImage("laser.png");
  img1 = loadImage("tmer.jpg");
  img2 = loadImage("etik.JPG");
  img3 = loadImage("cuts.jpeg");
  img4= loadImage("gap.png");
  img5= loadImage("bir.jpg");
     printArray(Serial.list());
  port=new Serial(this,"COM9",9600);
  cp5=new ControlP5(this);
printArray(Serial.list());
  cp5.addTextfield("etikit boyutu(mm)").setPosition(150, 300).setSize(100, 80).setAutoClear(false).setFont(createFont("arial", 11));
  cp5.addTextfield("gecikme(sanye)").setPosition(280, 300).setSize(100, 80).setAutoClear(false).setFont(createFont("arial", 11));
  cp5.addTextfield("kac adet").setPosition(410, 300).setSize(100, 80).setAutoClear(false).setFont(createFont("arial", 11));
  cp5.addTextfield("bosluk degeri ").setPosition(540, 300).setSize(100, 80).setAutoClear(false).setFont(createFont("arial", 11));
  cp5.addBang("kesmicek").setPosition(550, 600).setSize(200, 130).setFont(createFont("arial", 20));
  cp5.addBang("KESICEK").setPosition(50, 600).setSize(200, 130).setFont(createFont("arial", 20));
   cp5.addBang("biradet").setPosition(300, 600).setSize(200, 130).setFont(createFont("arial",20));
  /*cp5.addButton("STOP")  //the name of the led
  .setPosition(400,400)//x and y coordinates of the upper corner of button
  .setSize(100,70) //width and hight
  
  ;*/
}
public void draw() {
  background(100, 0, 100);
  move();
  display();

image(img, 0, 0, 800, 100+100);
  image(img1, 180+100, 250, 100, 100);
  image(img2, 50+100, 250, 100, 100);
  image(img3, 310+100, 250, 100, 100);
  image(img4, 440+100, 250, 100, 100);
  image(img5, 300,500, 200, 100);
  /*image(img5,50,400, 300,200);
   image(img6,350,400, 300,200);*/
  circle(15, 0.5f);
text("LAZER MAKINE KONTROL ARAYUZU",300,230);
 
  
}
public void KESICEK() {

  text1=cp5.get(Textfield.class, "etikit boyutu(mm)").getText();
    text2=cp5.get(Textfield.class, "gecikme(sanye)").getText();
  text3=cp5.get(Textfield.class, "kac adet").getText();
  text4=cp5.get(Textfield.class, "bosluk degeri ").getText();
  String ttext="";
  ttext="a"+text1+"b"+text2+"c"+text3+"d"+text4+"ikesj";

 port.write(ttext);
  /*println(ttext);
  println(ttext.getClass());*/
}
public void kesmicek() {

  text1=cp5.get(Textfield.class, "etikit boyutu(mm)").getText();
    text2=cp5.get(Textfield.class, "gecikme(sanye)").getText();
  text3=cp5.get(Textfield.class, "kac adet").getText();
  text4=cp5.get(Textfield.class, "bosluk degeri ").getText();
  String ttext="";
  ttext="a"+text1+"b"+text2+"c"+text3+"d"+text4+"ikesmj";

 port.write(ttext);
 /*println(ttext);
  println(ttext.getClass());*/
}
public void move() {
  x = x + speed;
  if (x>100) {
    x = 0;
  }
}

public void display() {
  fill(c);
  stroke(200);
  strokeWeight(10);
  rect(x, y, 160, 60);
}
public void circle( float r, float step)
{
  fill(c);

  line (x1, y1, x1+r, y1+0);

  float x11 = x1 +  r*cos(pos);
  float y11 = y1 +  r*sin(pos);

  ellipse(x11, y11, 80, 80);


  stroke(150);
  strokeWeight(10);

  pos+=step;
}
public void biradet()
{
   text1=cp5.get(Textfield.class, "etikit boyutu(mm)").getText();
    text2=cp5.get(Textfield.class, "gecikme(sanye)").getText();
  text3=cp5.get(Textfield.class, "kac adet").getText();
  text4=cp5.get(Textfield.class, "bosluk degeri ").getText();
  String ttext="";
  ttext="a"+text1+"b"+text2+"c"+text3+"d"+text4+"ibrj";

 port.write(ttext);
}
  public void settings() {  size(800, 800); }
  static public void main(String[] passedArgs) {
    String[] appletArgs = new String[] { "--present", "--window-color=#666666", "--stop-color=#cccccc", "KONTROL_KODU" };
    if (passedArgs != null) {
      PApplet.main(concat(appletArgs, passedArgs));
    } else {
      PApplet.main(appletArgs);
    }
  }
}
