"""Representative diagram for repeatable end-to-end tests (not a user upload)."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[1]

def make_fixture(path):
    im=Image.new('RGB',(1600,900),'#f6f7fc')
    d=ImageDraw.Draw(im)
    regular='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
    bold='/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
    def text(xy,s,size=20,color='#20294e',weight=False):
        d.text(xy,s,font=ImageFont.truetype(bold if weight else regular,size),fill=color)
    d.rectangle((0,0,159,900),fill='#1b2454')
    text((20,50),'GATEWAY',18,'white',True)
    text((20,76),'SECURITY',18,'white',True)
    text((18,270),'APPLICATION',16,'white',True)
    text((30,295),'SERVICES',16,'white',True)
    text((45,560),'DATA',18,'white',True)
    text((40,586),'LAYER',18,'white',True)
    d.rectangle((205,25,1550,83),fill='#34418c')
    text((738,40),'Secure Access Layer',24,'white',True)
    for x,label in [(220,'IAM / SSO'),(555,'RBAC + ABAC'),(890,'Threat Detection'),(1225,'Audit Logging')]:
        d.rectangle((x,105,x+300,160),outline='#505e98',width=2)
        text((x+45,122),label,19)
    headings=['Sourcing & Screening','Matching & Ranking','AI Video Assessment','Interview Management','Recruitment Dashboard']
    descriptions=['Job posting and AI screening','Competency based scoring','Structured video evaluation','Scheduling and stage tracking','Pipeline reporting and KPIs']
    for i in range(5):
        x=210+i*272
        d.rectangle((x,215,x+240,365),fill='white',outline='#505e98',width=2)
        d.rectangle((x+2,217,x+7,363),fill='#13b7c3')
        text((x+17,230),f'SERVICE 0{i+1}',13,'#16aabb',True)
        words=headings[i].split(); midpoint=2
        text((x+17,257),' '.join(words[:midpoint]),18,weight=True)
        text((x+17,281),' '.join(words[midpoint:]),18,weight=True)
        d.line((x+17,312,x+220,312),fill='#e0e1ec',width=1)
        words=descriptions[i].split()
        text((x+17,323),' '.join(words[:3]),12,'#888da0')
        text((x+17,340),' '.join(words[3:]),12,'#888da0')
        d.line((x+120,365,x+120,415),fill='#505e98',width=2)
        d.polygon([(x+114,406),(x+126,406),(x+120,419)],fill='#505e98')
    d.rectangle((205,420,1550,470),fill='#1b2454')
    text((605,435),'EVENT BUS / MESSAGE BROKER',21,'white',True)
    labels=['Candidate DB','Job & Req. DB','Assessment DB','Analytics Data Mart','Redis Cache']
    for i,label in enumerate(labels):
        x=210+i*272
        d.line((x+120,470,x+120,580),fill='#505e98',width=2)
        d.rectangle((x,600,x+240,680),fill='white',outline='#505e98',width=2)
        d.ellipse((x,580,x+240,620),fill='white',outline='#505e98',width=2)
        text((x+15,641),label,17,weight=True)
    d.rectangle((205,755,1550,865),fill='#1b2454')
    for x,label,sub in [(250,'Sovereignty','KSA Data Residency'),(580,'Compliance','PDPL NCA SAMA aligned'),(930,'Scalability','Elastic multi tenant'),(1240,'Observability','Full audit and monitoring')]:
        text((x,778),label,22,'white',True)
        text((x,820),sub,14,'#19b0bb')
    im.save(path)
    return im

if __name__=='__main__':
    folder=ROOT/'test-results'
    folder.mkdir(exist_ok=True)
    make_fixture(folder/'diagram.png')
    print(folder/'diagram.png')
