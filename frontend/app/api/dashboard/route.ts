import { readFile } from "fs/promises";
import path from "path";


export const dynamic = "force-dynamic";


export async function GET() {

  try {

    const filePath = path.join(
      process.cwd(),
      "data",
      "mock-dashboard.json"
    );


    const file = await readFile(
      filePath,
      "utf8"
    );


    const json = JSON.parse(file);


    return Response.json(json);


  } catch(error) {


    return Response.json(
      {
        error:
        "Cannot load dashboard data"
      },
      {
        status:500
      }
    );

  }

}