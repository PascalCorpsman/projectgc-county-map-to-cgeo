(******************************************************************************)
(* geojson_colorizer                                               06.05.2026 *)
(*                                                                            *)
(* Version     : 0.01                                                         *)
(*                                                                            *)
(* Author      : Uwe Schächterle (Corpsman)                                   *)
(*                                                                            *)
(* Support     : www.Corpsman.de                                              *)
(*                                                                            *)
(* Description : Tool to extract county lists from .geojson, and to colorize  *)
(*               counties in .geojson files                                   *)
(*                                                                            *)
(* License     : See the file license.md, located under:                      *)
(*  https://github.com/PascalCorpsman/Software_Licenses/blob/main/license.md  *)
(*  for details about the license.                                            *)
(*                                                                            *)
(*               It is not allowed to change or remove this text from any     *)
(*               source file of the project.                                  *)
(*                                                                            *)
(* Warranty    : There is no warranty, neither in correctness of the          *)
(*               implementation, nor anything other that could happen         *)
(*               or go wrong, use at your own risk.                           *)
(*                                                                            *)
(* Known Issues: none                                                         *)
(*                                                                            *)
(* History     : 0.01 - Initial version                                       *)
(*                                                                            *)
(******************************************************************************)
Unit Unit1;

{$MODE objfpc}{$H+}

Interface

Uses
  Classes, SysUtils, Forms, Controls, Graphics, Dialogs, StdCtrls, ExtCtrls,
  ugeojson;

Const
  Version = '0.01';

Type
  { TForm1 }

  TForm1 = Class(TForm)
    Button1: TButton;
    Button2: TButton;
    Button3: TButton;
    Button4: TButton;
    Button5: TButton;
    Button6: TButton;
    Button7: TButton;
    Button8: TButton;
    Edit1: TEdit;
    Edit2: TEdit;
    Edit3: TEdit;
    Edit4: TEdit;
    Memo1: TMemo;
    OpenDialog1: TOpenDialog;
    OpenDialog2: TOpenDialog;
    PaintBox1: TPaintBox;
    SaveDialog1: TSaveDialog;
    SaveDialog2: TSaveDialog;
    Procedure Button1Click(Sender: TObject);
    Procedure Button2Click(Sender: TObject);
    Procedure Button3Click(Sender: TObject);
    Procedure Button4Click(Sender: TObject);
    Procedure Button5Click(Sender: TObject);
    Procedure Button6Click(Sender: TObject);
    Procedure Button7Click(Sender: TObject);
    Procedure Button8Click(Sender: TObject);
    Procedure FormCreate(Sender: TObject);
    Procedure FormDestroy(Sender: TObject);
    Procedure PaintBox1Paint(Sender: TObject);
  private
    fobj: TGEOJSON;

  public

  End;

Var
  Form1: TForm1;

Implementation

{$R *.lfm}

Uses math, uvectormath;

{ TForm1 }

Procedure TForm1.Button1Click(Sender: TObject);
Var
  i: Integer;
  f: String;
Begin
  If Not OpenDialog1.Execute Then exit;
  f := OpenDialog1.FileName;
  If Not fobj.LoadGEOJSONFile(f) Then Begin
    showmessage('Error, could not load geojson file.');
  End;
  memo1.clear;
  memo1.append(format('MinLat: %0.5f', [fobj.Dim.MinLat]));
  memo1.append(format('MinLon: %0.5f', [fobj.Dim.MinLon]));
  memo1.append(format('MaxLat: %0.5f', [fobj.Dim.MaxLat]));
  memo1.append(format('MaxLon: %0.5f', [fobj.Dim.MaxLon]));
  memo1.append(format('Regions: %d', [length(fobj.Regions)]));
  For i := 0 To high(fobj.Colors) Do Begin
    memo1.append('Color: ' + fobj.Colors[i]);
  End;
  PaintBox1.Invalidate;
End;

Procedure TForm1.Button2Click(Sender: TObject);
Var
  LandKreise, T5er: TStringList;
  i, j: Integer;
  found: Boolean;
Begin
  LandKreise := TStringList.Create;
  LandKreise.LoadFromFile('Landkreise.txt');
  T5er := TStringList.Create;
  T5er.LoadFromFile('T5erLandkreise.txt');
  // 1. Alle Farben zurücksetzen
  For i := 0 To high(fobj.Regions) Do Begin
    fobj.Regions[i].Color := edit1.text;
  End;
  // 2. Alle Landkreise
  For i := 0 To LandKreise.Count - 1 Do Begin
    found := false;
    For j := 0 To high(fobj.Regions) Do Begin
      If fobj.Regions[j].Name = LandKreise[i] Then Begin
        fobj.Regions[j].Color := edit2.text;
        found := true;
        break;
      End;
    End;
    If Not found Then Begin
      Memo1.Append(LandKreise[i]);
    End;
  End;
  // 2. Alle T5er Landkreise
  For i := 0 To T5er.Count - 1 Do Begin
    found := false;
    For j := 0 To high(fobj.Regions) Do Begin
      If fobj.Regions[j].Name = T5er[i] Then Begin
        fobj.Regions[j].Color := edit3.text;
        found := true;
        break;
      End;
    End;
    If Not found Then Begin
      Memo1.Append(T5er[i]);
    End;
  End;

  T5er.free;
  LandKreise.free;
  PaintBox1.Invalidate;
End;

Procedure TForm1.Button3Click(Sender: TObject);
Begin
  If SaveDialog1.Execute Then Begin
    fobj.ExportAs(SaveDialog1.FileName);
  End;
End;

Procedure TForm1.Button4Click(Sender: TObject);
Var
  i: Integer;
Begin
  // 1. Alle Farben zurücksetzen
  For i := 0 To high(fobj.Regions) Do Begin
    fobj.Regions[i].Color := edit1.text;
  End;
  PaintBox1.Invalidate;
End;

Procedure TForm1.Button5Click(Sender: TObject);
Var
  List: TStringList;
  i, j: Integer;
  found: Boolean;
Begin
  If Not OpenDialog2.Execute Then exit;
  List := TStringList.Create;
  // 1. Laden
  List.LoadFromFile(OpenDialog2.FileName);
  // 2. Alle Landkreise
  For i := 0 To List.Count - 1 Do Begin
    found := false;
    For j := 0 To high(fobj.Regions) Do Begin
      If fobj.Regions[j].Name = List[i] Then Begin
        fobj.Regions[j].Color := edit2.text;
        found := true;
        break;
      End;
    End;
    If Not found Then Begin
      Memo1.Append(List[i]);
    End;
  End;
  List.free;
  PaintBox1.Invalidate;
End;

Procedure TForm1.Button6Click(Sender: TObject);
Var
  List: TStringList;
  i, j: Integer;
  found: Boolean;
Begin
  If Not OpenDialog2.Execute Then exit;
  List := TStringList.Create;
  // 1. Laden
  List.LoadFromFile(OpenDialog2.FileName);
  // 2. Alle Landkreise
  For i := 0 To List.Count - 1 Do Begin
    found := false;
    For j := 0 To high(fobj.Regions) Do Begin
      If fobj.Regions[j].Name = List[i] Then Begin
        fobj.Regions[j].Color := edit3.text;
        found := true;
        break;
      End;
    End;
    If Not found Then Begin
      Memo1.Append(List[i]);
    End;
  End;
  List.free;
  PaintBox1.Invalidate;
End;

Procedure TForm1.Button7Click(Sender: TObject);
Begin
  close;
End;

Procedure TForm1.Button8Click(Sender: TObject);
Var
  sl: TStringList;
  i: Integer;
Begin
  If SaveDialog2.Execute Then Begin
    sl := TStringList.Create;
    sl.Sorted := true;
    For i := 0 To high(fobj.Regions) Do Begin
      If fobj.Regions[i].Color = edit4.text Then Begin
        sl.add(fobj.Regions[i].Name);
      End;
    End;
    sl.SaveToFile(SaveDialog2.FileName);
    sl.free;
  End;
End;

Procedure TForm1.FormCreate(Sender: TObject);
Begin
  caption := 'Geojson colorizer ver. ' + version + ', by Corpsman, www.Corpsman.de';
  Memo1.Clear;
  fobj := TGEOJSON.create;
  edit1.text := '#ff3333';
  edit2.text := '#f0c20f';
  edit3.text := '#116611';
  edit4.text := '#116611';
End;

Procedure TForm1.FormDestroy(Sender: TObject);
Begin
  fobj.Free;
End;

Procedure TForm1.PaintBox1Paint(Sender: TObject);
Var
  i, j: Integer;
  dimw, dimh, w, h, x, y, scale, offsX, offsY, pbw, pbh: Single;
  col: TColor;
Begin
  pbw := PaintBox1.Width;
  pbh := PaintBox1.Height;
  dimw := fobj.Dim.MaxLon - fobj.Dim.MinLon;
  dimh := fobj.Dim.MaxLat - fobj.Dim.MinLat;
  // Keep geo aspect ratio, fit maximally into the available PaintBox area.
  If (dimw > 0) And (dimh > 0) And (pbw > 0) And (pbh > 0) Then Begin
    scale := min(pbw / dimw, pbh / dimh);
    w := dimw * scale;
    h := dimh * scale;
  End
  Else Begin
    w := pbw;
    h := pbh;
  End;
  offsX := (pbw - w) * 0.5;
  offsY := (pbh - h) * 0.5;
  PaintBox1.Canvas.Brush.Color := clWhite;
  PaintBox1.Canvas.Rectangle(-1, -1, PaintBox1.Width + 1, PaintBox1.Height + 1);
  For i := 0 To high(fobj.Regions) Do Begin
    For j := 0 To high(fobj.Regions[i].Points) Do Begin
      col := HTMLStringToColor(fobj.Regions[i].Color);
      x := ConvertDimension(fobj.Dim.MinLon, fobj.Dim.MaxLon, fobj.Regions[i].Points[j].Lon, 0, w) + offsX;
      y := ConvertDimension(fobj.Dim.MinLat, fobj.Dim.MaxLat, fobj.Regions[i].Points[j].Lat, h, 0) + offsY;
      PaintBox1.Canvas.Pixels[round(x), round(y)] := col;
    End;
  End;
End;

End.

