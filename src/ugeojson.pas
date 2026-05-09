Unit ugeojson;

{$MODE ObjFPC}{$H+}

Interface

Uses
  Classes, SysUtils, uJSON, Graphics;

Const
  InvalidLatLon = 1000; // Muss eine Zahl > 360 sein!

Type

  TDim = Record
    MinLat, MinLon: Double;
    MaxLat, MaxLon: Double;
  End;

  TDoublePoint = Record
    Lat, Lon: Double;
  End;

  TRegion = Record
    Name: String;
    Points: Array Of TDoublePoint;
    Color: String;
  End;

  { TGEOJSON }

  TGEOJSON = Class
  private
    fJSONContent: TJSONObj;
    Procedure CalcInternalData;
    Procedure StoreInternalData;
    Procedure Clear;
  public
    Colors: Array Of String;
    Dim: TDim;
    Regions: Array Of TRegion;
    Constructor Create; virtual;
    Destructor Destroy; override;
    Function LoadGEOJSONFile(Const aFilename: String): Boolean;
    Procedure ExportAs(Const aFilename: String);
  End;

Function HTMLStringToColor(col: String): TColor;

Implementation

Uses math;

Function HTMLStringToColor(col: String): TColor;
Var
  v, dummy: integer;
Begin
  result := 0;
  val('$' + copy(col, 2, 2), v, dummy);
  result := result + v * (1 Shl 0);
  val('$' + copy(col, 4, 2), v, dummy);
  result := result + v * (1 Shl 8);
  val('$' + copy(col, 6, 2), v, dummy);
  result := result + v * (1 Shl 16);
End;

{ TGEOJSON }

Procedure TGEOJSON.CalcInternalData;

  Procedure CalcFeatureDimension(Const jn: TJSONNode; Var Region: TRegion);
    Procedure TraverseArray(Const ja: TJSONArray);
    Var
      i: Integer;
      lat, lon: Double;
    Begin
      If ja.ObjCount = 0 Then exit;
      If ja.Obj[0] Is TJSONTerminal Then Begin
        If ja.ObjCount <> 2 Then Raise exception.create('Error, invalid data.');
        // Index 0 = lon
        // index 1 = lan
        lon := strtofloat((ja.obj[0] As TJSONTerminal).Value);
        lat := strtofloat((ja.obj[1] As TJSONTerminal).Value);
        Dim.MaxLat := max(Dim.MaxLat, lat);
        Dim.MaxLon := max(Dim.MaxLon, lon);
        Dim.MinLat := min(Dim.MinLat, lat);
        Dim.MinLon := min(Dim.MinLon, lon);
        setlength(Region.Points, high(Region.Points) + 2);
        Region.Points[high(Region.Points)].Lat := lat;
        Region.Points[high(Region.Points)].Lon := lon;
      End
      Else Begin
        For i := 0 To ja.ObjCount - 1 Do Begin
          TraverseArray(ja.Obj[i] As TJSONArray);
        End;
      End;
    End;
  Var
    ja: TJSONArray;
    col: String;
    i: Integer;
    found: Boolean;
  Begin
    region.Name := (jn.FindPath('properties.GEN') As TJSONValue).Value;
    col := (jn.FindPath('properties.fill') As TJSONValue).Value;
    region.Color := col;
    found := false;
    For i := 0 To high(Colors) Do Begin
      If Colors[i] = col Then found := true;
    End;
    If Not found Then Begin
      setlength(Colors, high(Colors) + 2);
      Colors[high(Colors)] := col;
    End;
    ja := jn.FindPath('geometry.coordinates') As TJSONArray;
    If Not assigned(ja) Then exit;
    TraverseArray(ja);
  End;

Var
  fja: TJSONArray;
  i: Integer;
Begin
  FormatSettings.DecimalSeparator := '.';
  Dim.MaxLat := -InvalidLatLon;
  Dim.MaxLon := -InvalidLatLon;
  Dim.MinLat := InvalidLatLon;
  Dim.MinLon := InvalidLatLon;
  If Not assigned(fJSONContent) Then exit;
  fja := fJSONContent.FindPath('features') As TJSONArray;
  If Not assigned(fja) Then exit;
  setlength(Regions, fja.ObjCount);
  For i := 0 To fja.ObjCount - 1 Do Begin
    // Je Landkreis
    CalcFeatureDimension(fja.Obj[i] As TJSONNode, regions[i]);
  End;
End;

Procedure TGEOJSON.StoreInternalData;
Var
  fja: TJSONArray;
  i: Integer;
  jn: TJSONNode;
  stroke, fill: TJSONValue;
Begin
  If Not assigned(fJSONContent) Then exit;
  fja := fJSONContent.FindPath('features') As TJSONArray;
  If Not assigned(fja) Then exit;
  setlength(Regions, fja.ObjCount);
  For i := 0 To fja.ObjCount - 1 Do Begin
    // Je Landkreis
    jn := fja.Obj[i] As TJSONNode;
    fill := jn.FindPath('properties.fill') As TJSONValue;
    fill.Value := regions[i].Color;
    stroke := jn.FindPath('properties.stroke') As TJSONValue;
    stroke.Value := regions[i].Color;
  End;
End;

Procedure TGEOJSON.Clear;
Var
  i: Integer;
Begin
  If assigned(fJSONContent) Then fJSONContent.free;
  fJSONContent := Nil;
  For i := 0 To high(Regions) Do Begin
    setlength(Regions[i].Points, 0);
  End;
  setlength(Regions, 0);
  setlength(Colors, 0);
End;

Constructor TGEOJSON.Create;
Begin
  Inherited Create;
  fJSONContent := Nil;
  Regions := Nil;
  Colors := Nil;
End;

Destructor TGEOJSON.Destroy;
Begin
  clear;
End;

Function TGEOJSON.LoadGEOJSONFile(Const aFilename: String): Boolean;
Var
  jp: TJSONParser;
  sl: TStringList;
Begin
  result := false;
  Clear;
  jp := TJSONParser.Create;
  sl := TStringList.Create;
  sl.LoadFromFile(aFilename);
  fJSONContent := jp.Parse(sl.Text);
  sl.free;
  jp.free;
  If Not assigned(fJSONContent) Then exit;
  CalcInternalData();
  result := true;
End;

Procedure TGEOJSON.ExportAs(Const aFilename: String);
Var
  sl: TStringList;
Begin
  StoreInternalData;
  sl := TStringList.Create;
  sl.Text := fJSONContent.ToString('', true);
  sl.SaveToFile(aFilename);
  sl.free;
End;

End.

